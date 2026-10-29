"""One trial: reset -> warm up under load -> inject fault -> detect -> recover -> measure."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from . import lab
from .actions import Action, run_action
from .analysis import (RecoveryCriteria, analyze, is_healthy, recent, recently_unhealthy,
                       window_summary)
from .config import API_URL
from .load import LoadGenerator
from .scenarios import Scenario


@dataclass(frozen=True)
class TrialResult:
    started_at: str
    scenario: str
    action: str
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


async def run_trial(scenario: Scenario, action: Action,
                    criteria: RecoveryCriteria = RecoveryCriteria(),
                    rate_per_s: float = 20, warmup_s: float = 15,
                    timeout_s: float = 60, detect_timeout_s: float = 15) -> TrialResult:
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await asyncio.to_thread(lab.reset)

    load = LoadGenerator(API_URL, rate_per_s)
    stop = asyncio.Event()
    load_task = asyncio.create_task(load.run(stop))
    detected_at = None
    action_result = None
    symptoms: dict = {}
    try:
        await asyncio.sleep(warmup_s)
        inject_at = load.now()
        await asyncio.to_thread(scenario.inject)

        while load.now() < inject_at + detect_timeout_s:
            await asyncio.sleep(0.2)
            if recently_unhealthy(load.samples, load.now(), criteria):
                detected_at = load.now()
                break

        if detected_at is not None:
            success, p95_ms = window_summary(recent(load.samples, load.now(), criteria))
            symptoms = {
                "sym_error_rate": None if success is None else 1 - success,
                "sym_p95_ms": p95_ms,
                **{f"sym_{k}": v for k, v in (await asyncio.to_thread(lab.probe)).items()},
            }
            # The load keeps running in the background while the playbook executes.
            action_result = await asyncio.to_thread(run_action, action)
            while load.now() < inject_at + timeout_s:
                # Only judge windows whose requests have all finished or timed out.
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

    def r(x: float | None) -> float | None:
        return None if x is None else round(x, 2)

    return TrialResult(
        started_at=started_at,
        scenario=scenario.name,
        action=action.name,
        valid=is_healthy(baseline, criteria),
        baseline_success=r(baseline_success),
        baseline_p95_ms=r(baseline_p95),
        impacted=result.impacted,
        detected_after_s=None if detected_at is None else r(detected_at - inject_at),
        action_ok=None if action_result is None else action_result.ok,
        action_duration_s=None if action_result is None else r(action_result.duration_s),
        recovered=result.recovered,
        recovery_time_s=r(result.recovery_time_s),
        incident_availability=r(result.incident_availability),
        incident_failures=result.incident_failures,
        incident_requests=result.incident_requests,
        incident_p95_ms=r(result.incident_p95_ms),
        **{k: r(v) if isinstance(v, float) else v for k, v in symptoms.items()},
    )
