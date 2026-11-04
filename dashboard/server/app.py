"""Evidence Dashboard API + static frontend.

Reads the shared experiment history (results volume) and can launch
experiments through the same runner the CLI uses (one at a time per lab).
It is also the operator's console for on-call mode: approvals, the SLO, and
the chaos side (unannounced faults, the chaos monkey).
"""
import math
import os
import random
import threading
import time
from datetime import datetime, timezone

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chaosctl import incidents, insights, lab, learning, llm, store
from chaosctl.actions import ACTIONS
from chaosctl.config import (ALERTMANAGER_URL, LAB_PROJECT, PROMETHEUS_URL, SAFETY_POLICY,
                             TOXIPROXY_URL)
from chaosctl.policies import MODEL_PATH, POLICIES
from chaosctl.runner import LabBusy, lab_lock, make_policy, run_one
from chaosctl.scenarios import SCENARIOS, TRAINING

STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")
app = FastAPI(title="CHAOS OS Evidence Dashboard")


# ---------------------------------------------------------------- read models

@app.get("/api/overview")
def overview() -> dict:
    rows = store.trials(limit=100000)
    valid = [r for r in rows if r["valid"]]
    times = sorted(r["recovery_time_s"] for r in valid if r["recovered"])
    return {
        "trials": len(rows),
        "valid": len(valid),
        "recovered": len(times),
        "median_recovery_s": times[len(times) // 2] if times else None,
        "safety_blocked": sum(r["safety_blocked"] or 0 for r in rows),
        "scenarios": [{"name": s.name, "description": s.description, "held_out": s.held_out}
                      for s in SCENARIOS.values()],
        "actions": [{"name": a.name, "description": a.description} for a in ACTIONS.values()],
        "policies": [{"name": n, "description": (p.__doc__ or "").strip().splitlines()[0]}
                     for n, p in POLICIES.items()],
        "llm_available": llm.available(),
        "model_trained": os.path.exists(MODEL_PATH),
    }


@app.get("/api/lab")
def lab_status() -> dict:
    services = []
    for line in lab.docker("ps", "-a", "--filter", f"label=com.docker.compose.project={LAB_PROJECT}",
                           "--filter", "label=com.docker.compose.oneoff=False",
                           "--format", '{{.Label "com.docker.compose.service"}}|{{.State}}|{{.Status}}'
                           ).splitlines():
        name, state, status = line.split("|", 2)
        if name != "dashboard":  # the observer, not part of the system under test
            services.append({"name": name, "state": state, "status": status})
    try:
        proxies = httpx.get(f"{TOXIPROXY_URL}/proxies", timeout=2).json()
        faults = [{"proxy": name, "enabled": p["enabled"],
                   "toxics": [t["type"] for t in p.get("toxics", [])]}
                  for name, p in proxies.items()]
    except httpx.HTTPError:
        faults = []
    active = incidents.active_incident()
    return {"probe": lab.probe(), "services": sorted(services, key=lambda s: s["name"]),
            "proxies": faults,
            "oncall": {"incident": active and {"id": active["id"], "status": active["status"]},
                       "approval": incidents.pending_approval() is not None}}


@app.get("/api/matrix")
def matrix() -> list[dict]:
    return store.summary("action")


@app.get("/api/policies")
def policies() -> list[dict]:
    return store.summary("policy")


@app.get("/api/trials")
def trials(limit: int = 200) -> list[dict]:
    return store.trials(limit)


@app.get("/api/trials/{trial_id}")
def trial(trial_id: int) -> dict:
    t = store.trial(trial_id)
    if t is None:
        raise HTTPException(404, "trial not found")
    return t


_curve_cache: dict = {"at": 0.0, "data": None}


@app.get("/api/learning-curve")
def learning_curve() -> dict:
    if _curve_cache["data"] is None or time.time() - _curve_cache["at"] > 60:
        _curve_cache.update(at=time.time(), data=learning.learning_curve())
    return _curve_cache["data"]


@app.get("/api/safety")
def safety_policy() -> dict:
    with open(SAFETY_POLICY) as f:
        policy = yaml.safe_load(f)
    blocked = [s for t in store.trials(limit=500) if t["safety_blocked"]
               for s in store.trial(t["id"])["steps"] if not s["allowed"]]
    return {"policy": policy, "blocked": blocked[:100]}


# ------------------------------------------------------------- AI write-ups

def _ai(fn, *args):
    try:
        return {"text": fn(*args)}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/api/insights/results")
def insights_results(refresh: bool = False) -> dict:
    return _ai(insights.explain_results, refresh)


@app.get("/api/insights/trial/{trial_id}")
def insights_trial(trial_id: int, refresh: bool = False) -> dict:
    return _ai(insights.explain_trial, trial_id, refresh)


class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """'Ask the lab anything': gpt-4o-mini answers from the measured data only."""
    return _ai(insights.ask, req.question)


@app.post("/api/lab/reset")
def reset_lab() -> dict:
    """Clear every fault and restart stopped services (refused while an experiment runs)."""
    try:
        with lab_lock(wait=False):
            lab.reset()
            incidents.clear_chaos()
    except LabBusy as exc:
        raise HTTPException(409, str(exc)) from None
    return lab_status()


# --------------------------------------------------------------------- jobs

class JobRequest(BaseModel):
    scenario: str
    policy: str | None = None
    action: str | None = None
    reps: int = 1
    timeout_s: float = 90


_job_lock = threading.Lock()
_job: dict = {"state": "idle"}


def _run_job(req: JobRequest) -> None:
    def on_event(kind: str, data: dict) -> None:
        _job["events"].append({"t": round(time.time() - _job["started"], 1), "kind": kind, **data})

    try:
        for rep in range(1, req.reps + 1):
            _job["rep"] = rep
            policy = make_policy(policy=req.policy, action=req.action)
            trial_id, result = run_one(SCENARIOS[req.scenario], policy, req.timeout_s,
                                       on_event=on_event, wait_for_lab=False)
            _job["trial_ids"].append(trial_id)
        _job["state"] = "done"
    except LabBusy as exc:
        _job.update(state="error", error=str(exc))
    except Exception as exc:  # report any failure to the UI instead of dying silently
        _job.update(state="error", error=f"{exc.__class__.__name__}: {exc}")
    finally:
        _job_lock.release()


@app.post("/api/jobs")
def start_job(req: JobRequest) -> dict:
    if req.scenario not in SCENARIOS:
        raise HTTPException(400, "unknown scenario")
    if bool(req.policy) == bool(req.action):
        raise HTTPException(400, "give exactly one of policy or action")
    if req.action and req.action not in ACTIONS or req.policy and req.policy not in POLICIES:
        raise HTTPException(400, "unknown policy or action")
    if not 1 <= req.reps <= 5:
        raise HTTPException(400, "reps must be 1-5")
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(409, "an experiment is already running")
    _job.clear()
    _job.update(state="running", request=req.model_dump(), started=time.time(), rep=0,
                events=[], trial_ids=[], error=None)
    threading.Thread(target=_run_job, args=(req,), daemon=True).start()
    return job()


@app.get("/api/jobs/current")
def job() -> dict:
    return {k: v for k, v in _job.items() if k != "started"}


@app.post("/api/train")
def train() -> dict:
    if not store.training_steps(set(TRAINING)):
        raise HTTPException(400, "no training data yet - run the fixed-action matrix first")
    model, n = learning.train()
    _curve_cache["data"] = None
    return {"steps": n, "actions": model.actions}


# ------------------------------------------------------------------ on-call

SLO_TARGET = 0.99          # see observability/prometheus/rules/slo.yml
PAGE_BURN_RATE = 14.4
FAULT_MAX_S = 300          # injected faults are rolled back after this long
ON_CALL_POLICIES = ["heuristic", "rule_based", "bandit", "llm", "llm_agent", "llm_agent_sre"]


def _prom(query: str) -> float | None:
    try:
        result = httpx.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query},
                           timeout=2).json()["data"]["result"]
        value = float(result[0]["value"][1]) if result else None
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return None
    return value if value is not None and math.isfinite(value) else None


def _slo() -> dict:
    """The SLO as Prometheus sees it: bad-request ratios, burn rates, 24 h budget."""
    budget = 1 - SLO_TARGET
    bad_20s, bad_1m = _prom("slo:bad_ratio:rate20s"), _prom("slo:bad_ratio:rate1m")
    bad_24h = _prom('sum(increase(shop_synthetic_requests_total{result!="good"}[24h]))')
    total_24h = _prom("sum(increase(shop_synthetic_requests_total[24h]))")
    rate = _prom("sum(rate(shop_synthetic_requests_total[2m]))")
    # The budget is 1% of the window's requests; while the 24 h window is still
    # filling, count the requests a full day of steady traffic would bring.
    expected = max(total_24h or 0, (rate or 0) * 86400)
    allowed = budget * expected if expected else None
    return {
        "target": SLO_TARGET,
        "page_burn_rate": PAGE_BURN_RATE,
        "good_1m": None if bad_1m is None else 1 - bad_1m,
        "burn_20s": None if bad_20s is None else bad_20s / budget,
        "burn_1m": None if bad_1m is None else bad_1m / budget,
        "budget_allowed": None if allowed is None else round(allowed),
        "budget_used": None if bad_24h is None else round(bad_24h),
        "budget_remaining": None if not allowed or bad_24h is None else 1 - bad_24h / allowed,
        "traffic_rate": rate,
    }


def _alerts() -> list[dict] | None:
    try:
        raw = httpx.get(f"{ALERTMANAGER_URL}/api/v2/alerts",
                        params={"active": "true", "silenced": "false", "inhibited": "false"},
                        timeout=2).json()
    except (httpx.HTTPError, ValueError):
        return None  # Alertmanager unreachable: say so instead of "no alerts"
    return [{"name": a["labels"].get("alertname"), "severity": a["labels"].get("severity"),
             "summary": a.get("annotations", {}).get("summary"), "started_at": a.get("startsAt")}
            for a in raw]


def _age_s(iso: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()


@app.get("/api/oncall")
def oncall_status() -> dict:
    seen = incidents.agent_seen_at()
    chaos = incidents.active_chaos()
    available = {"llm": llm.available(), "llm_agent": llm.available(), "llm_agent_sre": llm.available(),
                 "bandit": os.path.exists(MODEL_PATH)}
    return {
        "settings": incidents.settings(),
        "agent": {"online": bool(seen) and _age_s(seen) < 30, "seen_at": seen},
        "slo": _slo(),
        "alerts": _alerts(),
        "active": incidents.active_incident(),
        "approval": incidents.pending_approval(),
        "incidents": incidents.incidents(limit=30),
        "score": incidents.scorecard(),
        "chaos": chaos and {**chaos, "rollback_in_s": max(0, round(FAULT_MAX_S - _age_s(chaos["at"])))},
        "scenarios": [{"name": s.name, "description": s.description, "held_out": s.held_out}
                      for s in SCENARIOS.values()],
        "actions": {a.name: a.description for a in ACTIONS.values()},
        "policies": [{"name": p, "available": available.get(p, True)} for p in ON_CALL_POLICIES],
    }


@app.get("/api/oncall/incidents/{incident_id}")
def oncall_incident(incident_id: int) -> dict:
    record = incidents.incident(incident_id)
    if record is None:
        raise HTTPException(404, "incident not found")
    return record


@app.get("/api/insights/oncall/{incident_id}")
def insights_oncall(incident_id: int, refresh: bool = False) -> dict:
    return _ai(insights.explain_incident, incident_id, refresh)


class SettingsRequest(BaseModel):
    autopilot: bool | None = None
    policy: str | None = None
    monkey: bool | None = None
    monkey_every_min: int | None = None


@app.post("/api/oncall/settings")
def oncall_settings(req: SettingsRequest) -> dict:
    changes = req.model_dump(exclude_none=True)
    if "policy" in changes and changes["policy"] not in ON_CALL_POLICIES:
        raise HTTPException(400, "unknown policy")
    if "monkey_every_min" in changes and not 2 <= changes["monkey_every_min"] <= 120:
        raise HTTPException(400, "monkey interval must be 2-120 minutes")
    return incidents.update_settings(**changes)


class DecisionRequest(BaseModel):
    approve: bool


@app.post("/api/oncall/approvals/{approval_id}")
def decide_approval(approval_id: int, req: DecisionRequest, request: Request) -> dict:
    # Behind Caddy this is the logged-in user (header set by the proxy, not the browser).
    who = request.headers.get("x-remote-user") or "operator"
    try:
        return incidents.decide(approval_id, req.approve, who)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


def _inject(name: str, source: str) -> dict:
    """Break the lab without telling the agent. One fault at a time."""
    scenario = random.choice(list(SCENARIOS.values())) if name == "random" else SCENARIOS[name]
    with lab_lock(wait=False):
        if incidents.active_chaos():  # roll the previous fault back first
            lab.reset()
            incidents.clear_chaos()
        scenario.inject()
        event_id = incidents.record_chaos(scenario.name, source)
    return {"id": event_id, "scenario": scenario.name}


class BreakRequest(BaseModel):
    scenario: str = "random"


@app.post("/api/oncall/break")
def break_lab(req: BreakRequest) -> dict:
    if req.scenario != "random" and req.scenario not in SCENARIOS:
        raise HTTPException(400, "unknown scenario")
    try:
        return _inject(req.scenario, "manual")
    except LabBusy as exc:
        raise HTTPException(409, str(exc)) from None


def _chaos_loop() -> None:
    """Chaos monkey (random unannounced faults, when enabled) and fault rollback."""
    next_at = None
    while True:
        time.sleep(10)
        try:
            active = incidents.active_chaos()
            if active and _age_s(active["at"]) > FAULT_MAX_S:
                with lab_lock(wait=False):
                    lab.reset()
                    incidents.clear_chaos()
            config = incidents.settings()
            if not config["monkey"]:
                next_at = None
                continue
            if next_at is None:  # jittered, so faults don't arrive on a predictable beat
                next_at = time.time() + config["monkey_every_min"] * 60 * random.uniform(0.5, 1.5)
            if time.time() >= next_at and _job.get("state") != "running":
                _inject("random", "monkey")
                next_at = None
        except LabBusy:
            pass  # an experiment or incident owns the lab: try again next tick
        except Exception as exc:  # the monkey must never take the dashboard down
            print(f"[chaos] {exc.__class__.__name__}: {exc}", flush=True)


@app.on_event("startup")
def start_chaos_loop() -> None:
    threading.Thread(target=_chaos_loop, daemon=True).start()


# ------------------------------------------------------------------ frontend

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):  # unknown API routes must 404, not return the app shell
            raise HTTPException(404, "not found")
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
