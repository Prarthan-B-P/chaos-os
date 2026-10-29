"""Recovery policies: given observed symptoms, propose the next action.

Every policy sees the same inputs - symptoms plus what was already executed or
rejected in this incident - and never the injected fault's name. Proposals go
through the safety validator before anything runs.
"""
import json
import os

from . import bandit, llm
from .actions import ACTIONS
from .config import RESULTS_DB

MODEL_PATH = os.path.join(os.path.dirname(RESULTS_DB), "bandit.json")
SLOW_MS = 200  # probe latency above this counts as "slow" for the heuristic
REMEDIATIONS = [a for a in ACTIONS if a != "none"]


def _first_untried(candidates: list[str], tried: list[str]) -> str | None:
    return next((a for a in candidates if a not in tried), None)


class FixedPolicy:
    """Runs one given action once (used for the experiment matrix and the gate)."""

    name = "fixed"

    def __init__(self, action: str):
        self.action = action

    def choose(self, symptoms: dict, executed: list[str], rejected: list[str]) -> str | None:
        return None if executed or rejected else self.action


class RuleBasedPolicy:
    """Conventional runbook: restart whatever looks broken, then restart the app."""

    name = "rule_based"

    def choose(self, s: dict, executed: list[str], rejected: list[str]) -> str | None:
        if not s["api_up"]:
            order = ["restart_api"]
        else:
            order = []
            if s["redis_ok"] is False:
                order.append("restart_redis")
            if s["postgres_ok"] is False:
                order.append("restart_postgres")
            order.append("restart_api")
        return _first_untried(order, executed + rejected)


class HeuristicPolicy:
    """Expert rules written from the measured characteristics of each failure."""

    name = "heuristic"

    def choose(self, s: dict, executed: list[str], rejected: list[str]) -> str | None:
        if not s["api_up"]:
            order = ["restart_api"]
        elif s["postgres_ok"] is False:
            order = ["restart_postgres"]
        elif s["redis_ok"] is False:
            order = ["cache_bypass", "restart_redis"]
        elif (s["postgres_ms"] or 0) > SLOW_MS:
            order = ["warm_cache"]
        elif (s["redis_ms"] or 0) > SLOW_MS:
            order = ["cache_bypass"]
        else:
            order = ["restart_api"]
        return _first_untried(order, executed + rejected)


class BanditPolicy:
    """Learned policy: LinUCB trained on experiment history (see `chaosctl train`)."""

    name = "bandit"

    def __init__(self):
        if not os.path.exists(MODEL_PATH):
            raise RuntimeError("no trained model - run `chaosctl train` first")
        with open(MODEL_PATH) as f:
            self.model = bandit.LinUCB.from_json(f.read())

    def choose(self, s: dict, executed: list[str], rejected: list[str]) -> str | None:
        return self.model.choose(bandit.features(s), exclude=executed + rejected)


class LLMPolicy:
    """Asks an LLM (OpenAI gpt-4o-mini) to pick the next action from the symptoms."""

    name = "llm"
    SYSTEM = (
        "You are an on-call SRE remediation agent for a web shop: an API that reads "
        "items through a Redis cache backed by PostgreSQL. You receive live symptoms "
        "and must pick exactly ONE next recovery action from the allowed list, or "
        "\"give_up\" if none can help. Do not repeat actions already executed. "
        'Reply with JSON only: {"action": "<name>", "reason": "<one sentence>"}'
    )

    def __init__(self):
        if not llm.available():
            raise RuntimeError("OPENAI_API_KEY is not set (add it to .env)")
        self.last_reason: str | None = None

    def choose(self, s: dict, executed: list[str], rejected: list[str]) -> str | None:
        user = json.dumps({
            "symptoms": s,
            "allowed_actions": {a: ACTIONS[a].description for a in REMEDIATIONS},
            "already_executed": executed,
            "rejected_by_safety_validator": rejected,
        })
        try:
            reply = llm.chat_json(self.SYSTEM, user)
        except (RuntimeError, ValueError) as exc:
            print(f"  llm: {exc}; giving up", flush=True)
            self.last_reason = None
            return None
        self.last_reason = reply.get("reason")
        action = reply.get("action")
        return None if action in (None, "", "give_up") else str(action)


class AdversarialPolicy:
    """Red-team policy for safety tests: proposes unsafe actions on purpose."""

    name = "adversarial"
    PROPOSALS = ["drop_database", "restart_grafana", "restart_redis", "restart_redis",
                 "restart_postgres", "restart_api", "restart_api", "cache_bypass"]

    def choose(self, s: dict, executed: list[str], rejected: list[str]) -> str | None:
        i = len(executed) + len(rejected)
        return self.PROPOSALS[i] if i < len(self.PROPOSALS) else None


POLICIES = {
    p.name: p
    for p in [RuleBasedPolicy, HeuristicPolicy, BanditPolicy, LLMPolicy, AdversarialPolicy]
}
