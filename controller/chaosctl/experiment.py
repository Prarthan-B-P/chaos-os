"""One trial: reset -> warm up under load -> inject fault -> detect -> remediate -> measure.

Remediation is a loop, like real incident response: observe symptoms, ask the
policy for an action, check it with the safety validator, run it, wait up to
STEP_WINDOW_S for the service to heal, and if it hasn't, observe again.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import lab
from .actions import ACTIONS, run_action
from .analysis import (RecoveryCriteria, analyze, healthy_streak, is_healthy, recent,
                       recently_unhealthy, window_summary)
from .config import API_URL
from .load import LoadGenerator
from .safety import SafetyValidator
from .scenarios import Scenario

STEP_WINDOW_S = 20      # how long one action gets to show it worked
HEAL_STREAK_WINDOWS = 3  # healthy seconds that count as "this step worked"
MAX_REJECTIONS = 5       # stop asking a policy that keeps proposing unsafe actions


@dataclass(frozen=True)
class Step:
    step: int
    action: str
    allowed: bool
    verdict: str
    started_s: float | None = None    # relative to fault injection
    duration_s: float | None = None
    action_ok: bool | None = None
    healed: bool | None = None
    time_to_heal_s: float | None = None  # action start -> start of healthy streak
    reward: float | None = None
    note: str | None = None             # e.g. the LLM's stated reason
    symptoms: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TrialResult:
    started_at: str
    scenario: str
    action: str                     # first executed action ("none" if nothing ran)
    valid: bool                     # baseline was healthy before injection
    baseline_success: float | None
    baseline_p95_ms: float | None
    impacted: bool
    detected_after_s: float | None
    action_ok: bool | None
    action_duration_s: float | None
    recovered: bool
    recovery_time_s: float | None
    incident_availability: float
    incident_failures: int
    incident_requests: int
    incident_p95_ms: float | None
    # Symptoms observed at detection time - the context a policy may use.
    sym_error_rate: float | None = None
    sym_p95_ms: float | None = None
    sym_api_up: bool | None = None
    sym_redis_ok: bool | None = None
    sym_postgres_ok: bool | None = None
    sym_redis_ms: float | None = None
    sym_postgres_ms: float | None = None
    policy: str | None = None
    actions: str | None = None       # executed actions, comma separated
    blocked: str | None = None       # proposals rejected by the safety validator
    safety_blocked: int = 0
    steps: list[Step] = field(default_factory=list)


def _r(x):
    return round(x, 2) if isinstance(x, float) else x


async def _observe(load: LoadGenerator, criteria: RecoveryCriteria) -> dict:
    success, p95_ms = window_summary(recent(load.samples, load.now(), criteria))
    probe = await asyncio.to_thread(lab.probe)
    return {k: _r(v) for k, v in {
        "error_rate": None if success is None else 1 - success,
        "p95_ms": p95_ms,
        **probe,
    }.items()}


async def _wait_healed(load: LoadGenerator, criteria: RecoveryCriteria,
                       started: float, deadline: float) -> float | None:
    """Time the healthy streak began, if it begins within the step window."""
    until = min(started + STEP_WINDOW_S, deadline)
    while True:
        now = load.now()
        if healthy_streak(load.samples, now, criteria, HEAL_STREAK_WINDOWS):
            return max(started, now - HEAL_STREAK_WINDOWS * criteria.window_s)
        if now >= until:
            return None
        await asyncio.sleep(0.5)


async def run_trial(scenario: Scenario, policy, validator: SafetyValidator,
                    criteria: RecoveryCriteria = RecoveryCriteria(),
                    rate_per_s: float = 20, warmup_s: float = 15,
                    timeout_s: float = 60, detect_timeout_s: float = 15,
                    on_event=None) -> TrialResult:
    """Run one trial. `on_event(kind, data)` receives live progress (optional)."""
    loop = asyncio.get_running_loop()
    marks = {
        "injected": lambda d: f"💥 fault injected: {d['scenario']}",
        "action": lambda d: f"▶ {d['action']} ({policy.name})",
        "blocked": lambda d: f"⛔ blocked {d['action']}",
        "done": lambda d: "✓ recovered" if d["recovered"] else "✕ not recovered",
    }

    def emit(kind: str, data: dict) -> None:
        if on_event:
            on_event(kind, data)
        if kind in marks:  # fire-and-forget: never stall the load generator
            loop.run_in_executor(None, lab.annotate, marks[kind](data), [scenario.name, kind])

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    emit("reset", {})
    await asyncio.to_thread(lab.reset)

    load = LoadGenerator(API_URL, rate_per_s)
    stop = asyncio.Event()
    load_task = asyncio.create_task(load.run(stop))
    detected_at = None
    steps: list[Step] = []
    executed: list[str] = []
    rejected: list[str] = []
    try:
        emit("warmup", {"seconds": warmup_s})
        await asyncio.sleep(warmup_s)
        inject_at = load.now()
        await asyncio.to_thread(scenario.inject)
        emit("injected", {"scenario": scenario.name})
        deadline = inject_at + timeout_s

        while load.now() < inject_at + detect_timeout_s:
            await asyncio.sleep(0.2)
            if recently_unhealthy(load.samples, load.now(), criteria):
                detected_at = load.now()
                break

        if detected_at is not None:
            emit("detected", {"after_s": round(detected_at - inject_at, 2)})
            while load.now() < deadline and len(rejected) < MAX_REJECTIONS:
                symptoms = await _observe(load, criteria)
                proposal = await asyncio.to_thread(policy.choose, symptoms, executed, rejected)
                if proposal is None:
                    break
                note = getattr(policy, "last_reason", None)
                verdict = validator.check(proposal, executed)
                if not verdict.allowed:
                    rejected.append(proposal)
                    steps.append(Step(len(steps) + 1, proposal, False, verdict.reason,
                                      note=note, symptoms=symptoms))
                    emit("blocked", {"action": proposal, "reason": verdict.reason})
                    continue

                emit("action", {"action": proposal, "verdict": verdict.reason})
                started = load.now()
                result = await asyncio.to_thread(run_action, ACTIONS[proposal])
                executed.append(proposal)
                healed_at = await _wait_healed(load, criteria, started, deadline)
                time_to_heal = None if healed_at is None else healed_at - started
                reward = (0.0 if time_to_heal is None
                          else max(0.0, 1 - time_to_heal / STEP_WINDOW_S))
                steps.append(Step(
                    len(steps) + 1, proposal, True, verdict.reason,
                    started_s=_r(started - inject_at), duration_s=_r(result.duration_s),
                    action_ok=result.ok, healed=healed_at is not None,
                    time_to_heal_s=_r(time_to_heal),
                    reward=_r(reward - validator.cost(proposal)),
                    note=note, symptoms=symptoms,
                ))
                emit("step_done", {"action": proposal, "healed": healed_at is not None})
                if healed_at is not None:
                    break

            # Keep the load running until recovery is confirmed or time runs out.
            while load.now() < deadline:
                live = analyze(load.samples, inject_at, load.now() - load.timeout_s, criteria)
                if live.impacted and live.recovered:
                    break
                await asyncio.sleep(1)
        end_at = load.now()
    finally:
        stop.set()
        await load_task
        await asyncio.to_thread(lab.reset)

    baseline = [s for s in load.samples if inject_at - 10 <= s.sent_at < inject_at]
    baseline_success, baseline_p95 = window_summary(baseline)
    result = analyze(load.samples, inject_at, end_at, criteria)
    first = next((s for s in steps if s.allowed), None)
    detection_symptoms = steps[0].symptoms if steps else {}

    trial = TrialResult(
        started_at=started_at,
        scenario=scenario.name,
        action=first.action if first else "none",
        valid=is_healthy(baseline, criteria),
        baseline_success=_r(baseline_success),
        baseline_p95_ms=_r(baseline_p95),
        impacted=result.impacted,
        detected_after_s=None if detected_at is None else _r(detected_at - inject_at),
        action_ok=first.action_ok if first else None,
        action_duration_s=first.duration_s if first else None,
        recovered=result.recovered,
        recovery_time_s=_r(result.recovery_time_s),
        incident_availability=_r(result.incident_availability),
        incident_failures=result.incident_failures,
        incident_requests=result.incident_requests,
        incident_p95_ms=_r(result.incident_p95_ms),
        **{f"sym_{k}": v for k, v in detection_symptoms.items()},
        policy=policy.name,
        actions=",".join(executed),
        blocked=",".join(rejected),
        safety_blocked=len(rejected),
        steps=steps,
    )
    emit("done", {"recovered": trial.recovered, "recovery_time_s": trial.recovery_time_s})
    return trial
