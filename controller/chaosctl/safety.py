"""Safety validator: every proposed action is checked here before it runs.

Rules come from safety-policy.yml. The validator never trusts the proposer -
rule-based, learned, or LLM policies all go through the same checks.
"""
import fnmatch
import os
from dataclasses import dataclass

import yaml

from .actions import ACTIONS


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str


class SafetyValidator:
    def __init__(self, policy: dict, project: str):
        self.project = project
        self.allowed_projects = policy["environment"]["allowed_projects"]
        self.max_actions = int(policy["limits"]["max_actions_per_incident"])
        self.high_impact = os.environ.get("CHAOS_HIGH_IMPACT_APPROVAL",
                                          policy["approval"]["high_impact"])
        self.actions = policy["actions"]

    @classmethod
    def from_file(cls, path: str, project: str) -> "SafetyValidator":
        with open(path) as f:
            return cls(yaml.safe_load(f), project)

    def check(self, action: str, executed: list[str]) -> Verdict:
        if not any(fnmatch.fnmatchcase(self.project, p) for p in self.allowed_projects):
            return Verdict(False, f"environment '{self.project}' is not an approved lab")
        if action not in self.actions or action not in ACTIONS:
            return Verdict(False, f"'{action}' is not an approved action")
        if action in executed:
            return Verdict(False, f"'{action}' already ran in this incident (no repeat loops)")
        if len(executed) >= self.max_actions:
            return Verdict(False, f"budget of {self.max_actions} actions per incident used up")
        if self.actions[action]["impact"] == "high":
            if self.high_impact != "auto":
                return Verdict(False, f"'{action}' is high impact and needs human approval")
            return Verdict(True, "high impact: auto-approved in isolated lab")
        return Verdict(True, "allowed")

    def cost(self, action: str) -> float:
        return float(self.actions.get(action, {}).get("cost", 0.0))
