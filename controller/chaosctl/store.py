"""Experiment history in SQLite (one row per trial)."""
import os
import sqlite3
import statistics
from dataclasses import asdict, fields

from .config import RESULTS_DB
from .experiment import TrialResult

_COLUMNS = [f.name for f in fields(TrialResult)]


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(RESULTS_DB), exist_ok=True)
    conn = sqlite3.connect(RESULTS_DB)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS trials (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        f"{', '.join(_COLUMNS)})"
    )
    return conn


def save(result: TrialResult) -> None:
    with _connect() as conn:
        conn.execute(
            f"INSERT INTO trials ({', '.join(_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
            [asdict(result)[c] for c in _COLUMNS],
        )


def summary() -> list[dict]:
    """Per (scenario, action): trial count, recovery rate, recovery-time spread."""
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT scenario, action, recovered, recovery_time_s, incident_availability "
            "FROM trials WHERE valid = 1 ORDER BY scenario, action"
        ).fetchall()

    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault((row["scenario"], row["action"]), []).append(row)

    out = []
    for (scenario, action), trials in groups.items():
        times = [t["recovery_time_s"] for t in trials if t["recovered"]]
        out.append({
            "scenario": scenario,
            "action": action,
            "trials": len(trials),
            "recovered": len(times),
            "median_s": statistics.median(times) if times else None,
            "min_s": min(times) if times else None,
            "max_s": max(times) if times else None,
            "availability": statistics.mean(t["incident_availability"] for t in trials),
        })
    return out
