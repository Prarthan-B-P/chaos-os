"""Evidence Dashboard API + static frontend.

Reads the shared experiment history (results volume) and can launch
experiments through the same runner the CLI uses (one at a time per lab).
"""
import os
import threading
import time

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chaosctl import insights, lab, learning, llm, store
from chaosctl.actions import ACTIONS
from chaosctl.config import LAB_PROJECT, SAFETY_POLICY, TOXIPROXY_URL
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
    return {"probe": lab.probe(), "services": sorted(services, key=lambda s: s["name"]),
            "proxies": faults}


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


# ------------------------------------------------------------------ frontend

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):  # unknown API routes must 404, not return the app shell
            raise HTTPException(404, "not found")
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
