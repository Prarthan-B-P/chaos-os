"""AI write-ups (gpt-4o-mini): plain-English explanations of results and incidents.

The model only summarizes measured data passed to it; it is told not to invent
numbers. Responses are cached in SQLite so the dashboard doesn't re-ask.
"""
import json
from datetime import datetime, timezone

import yaml

from . import learning, llm, store
from .actions import ACTIONS
from .config import SAFETY_POLICY
from .scenarios import SCENARIOS

SYSTEM = (
    "You are a senior SRE writing for a resilience-engineering report. Explain the "
    "measured data you are given in clear, plain English for engineers and students. "
    "Use ONLY numbers present in the data; never invent figures. Be concise and "
    "specific, and call out limitations (small samples, lab conditions) honestly."
)


def _cached(key: str) -> str | None:
    with store.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS insights (key TEXT PRIMARY KEY, text TEXT, "
                     "created_at TEXT)")
        row = conn.execute("SELECT text FROM insights WHERE key = ?", (key,)).fetchone()
    return row["text"] if row else None


def _remember(key: str, text: str) -> None:
    with store.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO insights VALUES (?, ?, ?)",
                     (key, text, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def explain_trial(trial_id: int, refresh: bool = False) -> str:
    key = f"trial:{trial_id}"
    if not refresh and (text := _cached(key)):
        return text
    trial = store.trial(trial_id)
    if trial is None:
        raise ValueError(f"no trial {trial_id}")
    text = llm.chat(SYSTEM, (
        "Write a short incident post-mortem (4-6 sentences): what failed, what the "
        "policy observed, which actions it took (and any the safety validator "
        "blocked), whether and how fast the service recovered, and one lesson.\n\n"
        + json.dumps(trial, default=str)
    ))
    _remember(key, text)
    return text


ASK_SYSTEM = (
    "You are the CHAOS OS lab assistant. CHAOS OS injects failures into a demo web shop "
    "(API -> Redis cache -> PostgreSQL) under steady load (20 req/s), lets policies choose "
    "recovery actions, and measures recovery per request. Answer the user's question using "
    "ONLY the JSON data provided and quote exact numbers from it. If the data cannot answer "
    "the question, say so plainly and suggest the experiment that would. At most 120 words, "
    "plain text, no markdown headings."
)


def ask(question: str) -> str:
    """Answer a free-form question about the lab from its measured data (not cached)."""
    question = question.strip()[:500]
    if not question:
        raise ValueError("ask a question first")
    curve = learning.learning_curve(points=3, permutations=5)
    with open(SAFETY_POLICY) as f:
        safety = yaml.safe_load(f)
    context = {
        "failures": [{"name": s.name, "description": s.description, "held_out": s.held_out}
                     for s in SCENARIOS.values()],
        "recovery_actions": {a.name: a.description for a in ACTIONS.values()},
        "fixed_action_results": store.summary("action"),
        "policy_results": store.summary("policy"),
        "bandit_learning": {
            "logged_steps": curve["steps"],
            "final_accuracy": curve["curve"][-1]["accuracy"] if curve["curve"] else None,
            "fixed_rule_baselines": curve["baselines"],
            "best_measured_action_per_failure": curve.get("best"),
        },
        "safety_policy": safety,
        "recent_incidents": [
            {k: t[k] for k in ("id", "scenario", "policy", "actions", "blocked", "recovered",
                               "recovery_time_s", "incident_failures")}
            for t in store.trials(limit=15)
        ],
        "definitions": "recovery_time_s: fault injection -> sustained healthy traffic "
                       "(>=99% success, p95 <= 300 ms for 5 s). failed_requests: per incident.",
    }
    return llm.chat(ASK_SYSTEM, json.dumps(context, default=str) + "\n\nQuestion: " + question,
                    max_tokens=400)


def explain_results(refresh: bool = False) -> str:
    key = "results"
    if not refresh and (text := _cached(key)):
        return text
    data = {
        "per_fixed_action": store.summary("action"),
        "per_policy": store.summary("policy"),
        "notes": "recovery_time in seconds from fault injection; failed_requests per "
                 "trial at 20 req/s; held_out scenarios were never used for training.",
    }
    text = llm.chat(SYSTEM, (
        "Summarize these resilience experiment results in 3 short paragraphs: (1) which "
        "recovery action works for which failure and why, (2) how the policies "
        "(rule_based, heuristic, bandit, llm) compare, including on held-out scenarios, "
        "(3) safety validator findings and limitations.\n\n" + json.dumps(data, default=str)
    ), max_tokens=900)
    _remember(key, text)
    return text
