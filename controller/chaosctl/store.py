"""Experiment history in SQLite: one row per trial, one row per remediation step."""
import json
import os
import sqlite3
import statistics
from dataclasses import asdict, fields

from .config import RESULTS_DB
from .experiment import Step, TrialResult

_TRIAL_COLUMNS = [f.name for f in fields(TrialResult) if f.name != "steps"]
_STEP_COLUMNS = [f.name for f in fields(Step)]


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(RESULTS_DB), exist_ok=True)
    conn = sqlite3.connect(RESULTS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(f"CREATE TABLE IF NOT EXISTS trials (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 f"{', '.join(_TRIAL_COLUMNS)})")
    conn.execute(f"CREATE TABLE IF NOT EXISTS steps (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 f"trial_id INTEGER REFERENCES trials(id), {', '.join(_STEP_COLUMNS)})")
    # Additive migration: older databases get new columns (as NULL) instead of breaking.
    for table, columns in (("trials", _TRIAL_COLUMNS), ("steps", _STEP_COLUMNS)):
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column in columns:
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
    return conn


def save(result: TrialResult) -> int:
    row = asdict(result)
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO trials ({', '.join(_TRIAL_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _TRIAL_COLUMNS)})",
            [row[c] for c in _TRIAL_COLUMNS],
        )
        trial_id = cur.lastrowid
        for step in result.steps:
            values = asdict(step)
            values["symptoms"] = json.dumps(values["symptoms"])
            conn.execute(
                f"INSERT INTO steps (trial_id, {', '.join(_STEP_COLUMNS)}) "
                f"VALUES (?, {', '.join('?' for _ in _STEP_COLUMNS)})",
                [trial_id, *[values[c] for c in _STEP_COLUMNS]],
            )
    return trial_id


def summary(by: str = "action") -> list[dict]:
    """Per (scenario, action|policy): trial count, recovery rate and spread, failures."""
    if by not in ("action", "policy"):
        raise ValueError("by must be 'action' or 'policy'")
    where = "policy = 'fixed' OR policy IS NULL" if by == "action" else "policy != 'fixed'"
    with connect() as conn:
        rows = conn.execute(
            f"SELECT scenario, {by} AS key, recovered, recovery_time_s, incident_failures, "
            f"safety_blocked FROM trials WHERE valid = 1 AND ({where}) ORDER BY scenario, key"
        ).fetchall()

    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault((row["scenario"], row["key"]), []).append(row)

    out = []
    for (scenario, key), trials in groups.items():
        times = [t["recovery_time_s"] for t in trials if t["recovered"]]
        out.append({
            "scenario": scenario,
            by: key,
            "trials": len(trials),
            "recovered": len(times),
            "median_s": statistics.median(times) if times else None,
            "min_s": min(times) if times else None,
            "max_s": max(times) if times else None,
            "failed_requests": statistics.mean(t["incident_failures"] for t in trials),
            "safety_blocked": sum(t["safety_blocked"] or 0 for t in trials),
        })
    return out


def training_steps(scenarios: set[str]) -> list[dict]:
    """Executed steps from valid trials of the given scenarios, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT t.scenario, s.action, s.reward, s.symptoms FROM steps s "
            "JOIN trials t ON t.id = s.trial_id "
            "WHERE t.valid = 1 AND s.allowed = 1 AND s.reward IS NOT NULL ORDER BY s.id"
        ).fetchall()
    return [
        {"scenario": r["scenario"], "action": r["action"], "reward": r["reward"],
         "symptoms": json.loads(r["symptoms"])}
        for r in rows if r["scenario"] in scenarios
    ]


def trials(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM trials ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def trial(trial_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM trials WHERE id = ?", (trial_id,)).fetchone()
        if row is None:
            return None
        steps = conn.execute("SELECT * FROM steps WHERE trial_id = ? ORDER BY step",
                             (trial_id,)).fetchall()
    out = dict(row)
    out["steps"] = [{**dict(s), "symptoms": json.loads(s["symptoms"] or "{}")} for s in steps]
    return out
