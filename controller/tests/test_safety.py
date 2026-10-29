"""Safety validator: every rule must block what it claims to block."""
import os
import unittest
from unittest import mock

from chaosctl.safety import SafetyValidator

POLICY = {
    "environment": {"allowed_projects": ["chaosos", "chaosos-ci-*"]},
    "limits": {"max_actions_per_incident": 2},
    "approval": {"high_impact": "auto"},
    "actions": {
        "restart_redis": {"impact": "medium", "cost": 0.05},
        "cache_bypass": {"impact": "low", "cost": 0.05},
        "restart_postgres": {"impact": "high", "cost": 0.2},
        "restart_api": {"impact": "medium", "cost": 0.1},
    },
}


class SafetyValidatorTests(unittest.TestCase):
    def setUp(self):
        self.v = SafetyValidator(POLICY, "chaosos")

    def test_allows_listed_action(self):
        self.assertTrue(self.v.check("restart_redis", []).allowed)

    def test_blocks_unknown_action(self):
        verdict = self.v.check("drop_database", [])
        self.assertFalse(verdict.allowed)
        self.assertIn("not an approved action", verdict.reason)

    def test_blocks_action_missing_from_policy(self):
        self.assertFalse(self.v.check("warm_cache", []).allowed)  # real action, not in policy

    def test_blocks_repeat_in_same_incident(self):
        self.assertFalse(self.v.check("restart_redis", ["restart_redis"]).allowed)

    def test_enforces_action_budget(self):
        verdict = self.v.check("restart_api", ["restart_redis", "cache_bypass"])
        self.assertFalse(verdict.allowed)
        self.assertIn("budget", verdict.reason)

    def test_blocks_unapproved_environment(self):
        self.assertFalse(SafetyValidator(POLICY, "production").check("cache_bypass", []).allowed)

    def test_allows_ci_projects_by_pattern(self):
        self.assertTrue(SafetyValidator(POLICY, "chaosos-ci-1").check("cache_bypass", []).allowed)

    def test_high_impact_auto_approved_in_lab(self):
        verdict = self.v.check("restart_postgres", [])
        self.assertTrue(verdict.allowed)
        self.assertIn("auto-approved", verdict.reason)

    def test_high_impact_denied_when_approval_required(self):
        with mock.patch.dict(os.environ, {"CHAOS_HIGH_IMPACT_APPROVAL": "deny"}):
            verdict = SafetyValidator(POLICY, "chaosos").check("restart_postgres", [])
        self.assertFalse(verdict.allowed)
        self.assertIn("approval", verdict.reason)

    def test_cost_lookup(self):
        self.assertEqual(self.v.cost("restart_postgres"), 0.2)
        self.assertEqual(self.v.cost("unknown"), 0.0)


if __name__ == "__main__":
    unittest.main()
