"""On-call records in the shared results database: incidents, approvals,
chaos events and on-call settings.

The on-call agent and the dashboard run in separate containers and coordinate
only through these tables. The agent never reads chaos_events: it learns about
failures the way an on-call engineer does, from alerts and its own checks. The
chaos log exists so the dashboard can score it (time to detect / recover).
"""
import json
import statistics
from datetime import datetime, timedelta, timezone

from . import store

DEFAULT_SETTINGS = {
    "autopilot": True,       # the agent acts on pages (off = it only watches)
    "policy": "heuristic",   # responder the agent uses
    "monkey": False,         # the dashboard injects random faults, unannounced
    "monkey_every_min": 10,
}
OPEN = ("investigating", "awaiting_approval")
MATCH_WINDOW_S = 600  # an incident opened this long after a fault is credited to it

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, opened_at TEXT, closed_at TEXT, status TEXT,
    alert TEXT, summary TEXT, alert_started_at TEXT, policy TEXT, actions TEXT,
    blocked TEXT, recovered INTEGER, recovered_at TEXT, mitigation_s REAL,
    probe_requests INTEGER, probe_failures INTEGER, timeline TEXT, steps TEXT,
    postmortem TEXT);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id INTEGER REFERENCES incidents(id),
    action TEXT, note TEXT, symptoms TEXT, requested_at TEXT, expires_at TEXT,
    decision TEXT, decided_at TEXT, decided_by TEXT);
CREATE TABLE IF NOT EXISTS chaos_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, scenario TEXT, source TEXT,
    cleared_at TEXT);
"""
_JSON_FIELDS = ("timeline", "steps", "symptoms")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _ts(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso) if iso else None


def _connect():
    conn = store.connect()
    conn.executescript(_SCHEMA)
    return conn


def _row(row) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for key in _JSON_FIELDS:
        if key in out:
            out[key] = json.loads(out[key]) if out[key] else ([] if key != "symptoms" else {})
    return out


def _encode(fields: dict) -> dict:
    return {k: json.dumps(v, default=str) if k in _JSON_FIELDS else v for k, v in fields.items()}


# ------------------------------------------------------------------ settings

def settings() -> dict:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    saved = {r["key"]: json.loads(r["value"]) for r in rows if r["key"] in DEFAULT_SETTINGS}
    return {**DEFAULT_SETTINGS, **saved}


def update_settings(**changes) -> dict:
    with _connect() as conn:
        for key, value in changes.items():
            if key in DEFAULT_SETTINGS:
                conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
    return settings()


def heartbeat() -> None:
    """The agent checks in regularly so the dashboard can show it is alive."""
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES ('agent_seen_at', ?)", (json.dumps(now()),))


def agent_seen_at() -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'agent_seen_at'").fetchone()
    return json.loads(row["value"]) if row else None


# ----------------------------------------------------------------- incidents

def open_incident(**fields) -> int:
    fields = _encode({"opened_at": now(), "status": "investigating", **fields})
    with _connect() as conn:
        cur = conn.execute(f"INSERT INTO incidents ({', '.join(fields)}) "
                           f"VALUES ({', '.join('?' for _ in fields)})", list(fields.values()))
    return cur.lastrowid


def update_incident(incident_id: int, **fields) -> None:
    fields = _encode(fields)
    with _connect() as conn:
        conn.execute(f"UPDATE incidents SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                     [*fields.values(), incident_id])


def incident(incident_id: int) -> dict | None:
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone())


def incidents(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def active_incident() -> dict | None:
    """The incident the agent is working on, or an escalation still waiting for a human."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE status IN (?, ?) OR (status = 'escalated' AND closed_at IS NULL) "
            "ORDER BY id DESC LIMIT 1", OPEN).fetchone()
    return _row(row)


def open_escalation() -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM incidents WHERE status = 'escalated' AND closed_at IS NULL "
                           "ORDER BY id DESC LIMIT 1").fetchone()
    return _row(row)


# ----------------------------------------------------------------- approvals

def request_approval(incident_id: int, action: str, note: str | None, symptoms: dict,
                     timeout_s: float) -> int:
    requested = datetime.now(timezone.utc)
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO approvals (incident_id, action, note, symptoms, requested_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (incident_id, action, note, json.dumps(symptoms, default=str),
             requested.isoformat(timespec="milliseconds"),
             (requested + timedelta(seconds=timeout_s)).isoformat(timespec="milliseconds")))
    return cur.lastrowid


def approval(approval_id: int) -> dict | None:
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())


def pending_approval() -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM approvals WHERE decision IS NULL AND expires_at > ? "
                           "ORDER BY id DESC LIMIT 1", (now(),)).fetchone()
    return _row(row)


def decide(approval_id: int, approve: bool, by: str) -> dict:
    """Record a human decision; only the first decision (or expiry) counts."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE approvals SET decision = ?, decided_at = ?, decided_by = ? "
            "WHERE id = ? AND decision IS NULL AND expires_at > ?",
            ("approved" if approve else "denied", now(), by, approval_id, now()))
    if cur.rowcount == 0:
        raise ValueError("this approval was already decided or has expired")
    return approval(approval_id)


def expire(approval_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE approvals SET decision = 'expired', decided_at = ? "
                     "WHERE id = ? AND decision IS NULL", (now(), approval_id))


# -------------------------------------------------------------- chaos events

def record_chaos(scenario: str, source: str) -> int:
    with _connect() as conn:
        cur = conn.execute("INSERT INTO chaos_events (at, scenario, source) VALUES (?, ?, ?)",
                           (now(), scenario, source))
    return cur.lastrowid


def active_chaos() -> dict | None:
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM chaos_events WHERE cleared_at IS NULL "
                                 "ORDER BY id DESC LIMIT 1").fetchone())


def clear_chaos() -> None:
    """Mark every injected fault as rolled back (after a lab reset)."""
    with _connect() as conn:
        conn.execute("UPDATE chaos_events SET cleared_at = ? WHERE cleared_at IS NULL", (now(),))


def chaos_events(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM chaos_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def first_incident_since(iso: str) -> dict | None:
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM incidents WHERE opened_at >= ? ORDER BY id LIMIT 1",
                                 (iso,)).fetchone())


# ------------------------------------------------------------------- scoring

def _seconds(later: str | None, earlier: str | None) -> float | None:
    a, b = _ts(later), _ts(earlier)
    return None if a is None or b is None else round((a - b).total_seconds(), 1)


def scorecard(limit: int = 200) -> dict:
    """How the agent did against faults it was never told about.

    Each fault in the chaos log is matched to the first incident the agent opened
    after it: time to detect (alert fired), engage (agent on it) and recover.
    """
    events = list(reversed(chaos_events(limit)))
    all_incidents = list(reversed(incidents(limit)))
    rows, used = [], set()
    for e in events:
        start = _ts(e["at"])
        match = next((i for i in all_incidents if i["id"] not in used
                      and 0 <= (_ts(i["opened_at"]) - start).total_seconds() <= MATCH_WINDOW_S), None)
        if match:
            used.add(match["id"])
        rows.append({
            "event": e,
            "incident_id": match["id"] if match else None,
            "status": match["status"] if match else None,
            "detect_s": _seconds(match and match["alert_started_at"], e["at"]),
            "engage_s": _seconds(match and match["opened_at"], e["at"]),
            "recover_s": _seconds(match and match["recovered_at"], e["at"]),
        })

    def median(key):
        values = [r[key] for r in rows if r[key] is not None]
        return statistics.median(values) if values else None

    handled = [i for i in all_incidents if i["status"] not in OPEN]
    mitigations = [i["mitigation_s"] for i in handled if i["recovered"]]
    with _connect() as conn:
        decisions = dict(conn.execute("SELECT decision, COUNT(*) FROM approvals "
                                      "WHERE decision IS NOT NULL GROUP BY decision").fetchall())
    return {
        "faults": len(rows),
        "caught": sum(r["incident_id"] is not None for r in rows),
        "healed": sum(r["status"] == "resolved" for r in rows),
        "median_detect_s": median("detect_s"),
        "median_recover_s": median("recover_s"),
        "incidents": len(handled),
        "resolved": sum(i["status"] == "resolved" for i in handled),
        "escalated": sum(i["status"] == "escalated" for i in handled),
        "median_mitigation_s": statistics.median(mitigations) if mitigations else None,
        "approvals": decisions,
        "matches": list(reversed(rows))[:25],
    }
