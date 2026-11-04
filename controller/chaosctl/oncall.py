"""On-call mode: an always-on agent that heals failures nobody announced.

Experiments know what they broke and when. Here the agent only sees what an
on-call engineer sees: an SLO burn-rate page from Prometheus (delivered by
Alertmanager's webhook), the API's health endpoint, and its own probe traffic.

  page -> confirm with live probe traffic -> remediate (the experiments' loop and
  safety validator; high-impact actions wait for a human decision in the
  dashboard) -> confirm sustained recovery -> record -> AI post-mortem

The agent never reads the chaos log, so it cannot cheat: every incident it
handles was detected from symptoms alone.
"""
import asyncio
import json
import queue
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import incidents, insights, lab, llm
from .analysis import RecoveryCriteria, analyze, healthy_streak, recent, window_summary
from .config import API_URL
from .experiment import remediate
from .load import LoadGenerator
from .runner import LabBusy, lab_lock, make_policy, validator
from .safety import Verdict

PORT = 8095
PROBE_RATE = 10            # verification requests/s while the agent is engaged
CONFIRM_S = 4              # probe this long before believing (or dismissing) a page
INCIDENT_TIMEOUT_S = 180   # then hand the incident to a human
GRACE_S = 20               # after the last step: time for sustained recovery to show

_notifications: queue.Queue = queue.Queue()

MARKS = {  # Grafana annotations, next to the experiments' ones
    "alert": lambda d: f"🚨 on-call paged: {d['name']}",
    "action": lambda d: f"▶ {d['action']} (on-call)",
    "blocked": lambda d: f"⛔ blocked {d['action']}",
    "resolved": lambda d: f"✓ on-call mitigated in {d['mitigation_s']}s",
    "escalated": lambda d: "✕ on-call escalated to a human",
}


def log(message: str) -> None:
    print(f"[on-call] {message}", flush=True)


class _Webhook(BaseHTTPRequestHandler):
    """POST /alerts: Alertmanager's webhook. GET /healthz: Docker's health check."""

    def do_POST(self):
        if self.path != "/alerts":
            return self.send_error(404)
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError:
            return self.send_error(400)
        _notifications.put(payload)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path != "/healthz":
            return self.send_error(404)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # the container log is for incidents, not HTTP noise
        pass


def _latest_alerts(first: dict) -> list[dict]:
    """Current state of every alert across all queued notifications (newest wins)."""
    latest: dict[str, dict] = {}
    payload = first
    while payload is not None:
        for alert in payload.get("alerts", []):
            latest[alert.get("fingerprint") or alert["labels"].get("alertname", "")] = alert
        try:
            payload = _notifications.get_nowait()
        except queue.Empty:
            payload = None
    return list(latest.values())


def _is_page(alert: dict) -> bool:
    return alert.get("labels", {}).get("severity") == "page"


def serve() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), _Webhook)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"on call: listening for Alertmanager on :{PORT}")
    while True:
        incidents.heartbeat()
        try:
            first = _notifications.get(timeout=10)
        except queue.Empty:
            continue
        alerts = [a for a in _latest_alerts(first) if _is_page(a)]
        firing = [a for a in alerts if a.get("status") == "firing"]
        if firing:
            handle(firing)
        elif alerts and (escalation := incidents.open_escalation()):
            # The page resolved while a human owned the incident: close it.
            _close_escalation(escalation, "page resolved: service healthy again")


def handle(pages: list[dict]) -> None:
    config = incidents.settings()
    if not config["autopilot"]:
        log("autopilot is off: leaving the page to a human")
        return
    try:
        with lab_lock(wait=False):
            incident_id = asyncio.run(_respond(pages, config["policy"]))
    except LabBusy:
        log("the lab is busy (an experiment owns it): standing down")
        return
    if incident_id is not None and llm.available():
        try:
            insights.explain_incident(incident_id)
            log(f"incident #{incident_id}: post-mortem written")
        except (RuntimeError, ValueError) as exc:
            log(f"incident #{incident_id}: no post-mortem ({exc})")


def _close_escalation(escalation: dict, why: str) -> None:
    timeline = escalation["timeline"] + [{"t": None, "kind": "closed", "why": why}]
    incidents.update_incident(escalation["id"], closed_at=incidents.now(), timeline=timeline)
    log(f"incident #{escalation['id']}: {why}")


async def _respond(pages: list[dict], policy_name: str) -> int | None:
    """Confirm the page with live traffic; open and work an incident if it is real."""
    page = pages[0]
    name = page["labels"].get("alertname", "page")
    opened_at = incidents.now()
    criteria = RecoveryCriteria()
    load = LoadGenerator(API_URL, PROBE_RATE)
    stop = asyncio.Event()
    load_task = asyncio.create_task(load.run(stop))
    try:
        await asyncio.sleep(CONFIRM_S)
        healthy = healthy_streak(load.samples, load.now(), criteria, windows=3)
        if escalation := incidents.open_escalation():
            if healthy:
                _close_escalation(escalation, "service healthy again")
            else:
                log(f"incident #{escalation['id']} is with a human: not acting again")
            return None
        if healthy:
            log(f"{name}: not confirmed, live probe is healthy (stale page): no incident")
            return None
        return await _work_incident(page, name, opened_at, policy_name, load, criteria)
    finally:
        stop.set()
        await load_task


async def _work_incident(page: dict, name: str, opened_at: str, policy_name: str,
                         load: LoadGenerator, criteria: RecoveryCriteria) -> int:
    loop = asyncio.get_running_loop()
    epoch = time.time() - load.now()  # wall-clock time of the first probe request
    incident_id = incidents.open_incident(
        opened_at=opened_at, alert=name,
        summary=page.get("annotations", {}).get("summary"),
        alert_started_at=page.get("startsAt"), policy=policy_name)
    timeline: list[dict] = []

    def emit(kind: str, data: dict, t: float | None = None) -> None:
        timeline.append({"t": round(load.now() if t is None else t, 1), "kind": kind, **data})
        incidents.update_incident(incident_id, timeline=timeline)
        if kind in MARKS:  # fire-and-forget, like experiments
            loop.call_soon_threadsafe(loop.run_in_executor, None, lab.annotate,
                                      MARKS[kind](data), ["on-call", kind])

    success, p95_ms = window_summary(recent(load.samples, load.now(), criteria))
    emit("alert", {"name": name, "started_at": page.get("startsAt")}, t=0.0)  # the page itself
    emit("confirmed", {"error_rate": None if success is None else round(1 - success, 2),
                       "p95_ms": None if p95_ms is None else round(p95_ms)})
    log(f"incident #{incident_id}: {name} confirmed by live probe")

    try:
        policy = make_policy(policy_name)
    except (RuntimeError, ValueError) as exc:
        emit("fallback", {"policy": policy_name, "reason": str(exc), "using": "heuristic"})
        policy = make_policy("heuristic")
    rules = validator(on_call=True)

    def approve(action: str, symptoms: dict, note: str | None) -> Verdict:
        return _ask_human(incident_id, action, symptoms, note, rules.approval_timeout_s, emit)

    t0 = load.now()
    steps, executed, rejected = await remediate(load, criteria, policy, rules, t0,
                                                t0 + INCIDENT_TIMEOUT_S, emit, approve)

    # Close only on sustained recovery (5 healthy seconds), as experiments do.
    until = min(t0 + INCIDENT_TIMEOUT_S, load.now() + GRACE_S)
    result = analyze(load.samples, 0.0, load.now() - load.timeout_s, criteria)
    while not result.recovered and load.now() < until:
        await asyncio.sleep(1)
        result = analyze(load.samples, 0.0, load.now() - load.timeout_s, criteria)

    fields = dict(actions=",".join(executed), blocked=",".join(rejected),
                  steps=[asdict(s) for s in steps], probe_requests=result.incident_requests,
                  probe_failures=result.incident_failures, recovered=int(result.recovered))
    if result.recovered:
        mitigation_s = round(result.recovery_time_s, 1)
        recovered_at = datetime.fromtimestamp(epoch + result.recovery_time_s, timezone.utc)
        emit("resolved", {"mitigation_s": mitigation_s})
        incidents.update_incident(incident_id, status="resolved", closed_at=incidents.now(),
                                  recovered_at=recovered_at.isoformat(timespec="milliseconds"),
                                  mitigation_s=mitigation_s, timeline=timeline, **fields)
        log(f"incident #{incident_id}: mitigated in {mitigation_s}s ({fields['actions'] or 'no action'})")
    else:
        emit("escalated", {"reason": "no safe action restored the service"})
        incidents.update_incident(incident_id, status="escalated", timeline=timeline, **fields)
        log(f"incident #{incident_id}: escalated to a human")
    return incident_id


def _ask_human(incident_id: int, action: str, symptoms: dict, note: str | None,
               timeout_s: float, emit) -> Verdict:
    """Hold a high-impact action until someone decides in the dashboard (fail safe)."""
    approval_id = incidents.request_approval(incident_id, action, note, symptoms, timeout_s)
    incidents.update_incident(incident_id, status="awaiting_approval")
    log(f"incident #{incident_id}: {action} needs a human decision (approval #{approval_id})")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and not incidents.approval(approval_id)["decision"]:
        time.sleep(1)
    incidents.expire(approval_id)  # no-op if someone decided
    decision = incidents.approval(approval_id)
    incidents.update_incident(incident_id, status="investigating")
    if decision["decision"] == "approved":
        emit("approved", {"action": action, "by": decision["decided_by"]})
        return Verdict(True, f"approved by {decision['decided_by']}")
    if decision["decision"] == "denied":
        emit("denied", {"action": action, "by": decision["decided_by"]})
        return Verdict(False, f"denied by {decision['decided_by']}")
    emit("expired", {"action": action, "timeout_s": timeout_s})
    return Verdict(False, f"no human decision within {timeout_s:.0f}s: not run (fail safe)")
