"""On-call mode: human approvals in the remediation loop, and the shared records."""
import asyncio
import os
import tempfile
import unittest
from unittest import mock

from chaosctl import experiment, incidents, store
from chaosctl.actions import ActionResult
from chaosctl.safety import SafetyValidator, Verdict

POLICY = {
    "environment": {"allowed_projects": ["chaosos"]},
    "limits": {"max_actions_per_incident": 3},
    "approval": {"high_impact": "auto", "on_call": "human", "timeout_s": 30},
    "actions": {
        "restart_postgres": {"impact": "high", "cost": 0.2},
        "restart_api": {"impact": "medium", "cost": 0.1},
    },
}
SYMPTOMS = {"error_rate": 1.0, "p95_ms": 2000, "api_up": True, "redis_ok": True,
            "postgres_ok": False, "redis_ms": 1.0, "postgres_ms": 2000}


class FakeLoad:
    """Just a clock: the loop's observations and waits are patched out."""
    timeout_s = 2.0
    samples: list = []

    def now(self) -> float:
        return 1.0


class OrderPolicy:
    name = "test"

    def __init__(self, order):
        self.order = order

    def choose(self, symptoms, executed, rejected):
        return next((a for a in self.order if a not in executed + rejected), None)


def run(policy, validator, approve=None):
    async def observe(*_):
        return SYMPTOMS

    async def healed(_load, _criteria, started, _deadline):
        return started  # every executed action heals instantly

    ran = []
    with mock.patch.object(experiment, "_observe", observe), \
            mock.patch.object(experiment, "_wait_healed", healed), \
            mock.patch.object(experiment, "run_action",
                              lambda a: ran.append(a.name) or ActionResult(True, 0.1, "")):
        steps, executed, rejected = asyncio.run(experiment.remediate(
            FakeLoad(), experiment.RecoveryCriteria(), policy, validator, 0.0, 100.0,
            lambda *_: None, approve))
    return steps, executed, rejected, ran


class OnCallValidatorTests(unittest.TestCase):
    def test_on_call_mode_asks_a_human_for_high_impact(self):
        verdict = SafetyValidator(POLICY, "chaosos", on_call=True).check("restart_postgres", [])
        self.assertFalse(verdict.allowed)
        self.assertTrue(verdict.needs_approval)

    def test_experiments_keep_auto_approval(self):
        verdict = SafetyValidator(POLICY, "chaosos").check("restart_postgres", [])
        self.assertTrue(verdict.allowed)
        self.assertFalse(verdict.needs_approval)

    def test_deny_mode_never_asks(self):
        with mock.patch.dict(os.environ, {"CHAOS_HIGH_IMPACT_APPROVAL": "deny"}):
            verdict = SafetyValidator(POLICY, "chaosos", on_call=True).check("restart_postgres", [])
        self.assertFalse(verdict.allowed)
        self.assertFalse(verdict.needs_approval)

    def test_approval_timeout_comes_from_policy(self):
        self.assertEqual(SafetyValidator(POLICY, "chaosos", on_call=True).approval_timeout_s, 30)


class ApprovalLoopTests(unittest.TestCase):
    def setUp(self):
        self.validator = SafetyValidator(POLICY, "chaosos", on_call=True)
        self.policy = OrderPolicy(["restart_postgres", "restart_api"])

    def test_approved_action_runs(self):
        steps, executed, rejected, ran = run(self.policy, self.validator,
                                             lambda *_: Verdict(True, "approved by tester"))
        self.assertEqual(ran, ["restart_postgres"])
        self.assertEqual(steps[0].verdict, "approved by tester")
        self.assertEqual(rejected, [])

    def test_denied_action_never_runs_and_the_loop_moves_on(self):
        steps, executed, rejected, ran = run(self.policy, self.validator,
                                             lambda *_: Verdict(False, "denied by tester"))
        self.assertEqual(ran, ["restart_api"])
        self.assertEqual(rejected, ["restart_postgres"])
        self.assertFalse(steps[0].allowed)

    def test_without_an_approver_high_impact_stays_blocked(self):
        _, _, rejected, ran = run(self.policy, self.validator)
        self.assertNotIn("restart_postgres", ran)
        self.assertIn("restart_postgres", rejected)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(store, "RESULTS_DB", os.path.join(self.tmp.name, "chaos.db"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_settings_default_and_persist(self):
        self.assertTrue(incidents.settings()["autopilot"])
        incidents.update_settings(autopilot=False, policy="bandit", unknown=1)
        saved = incidents.settings()
        self.assertFalse(saved["autopilot"])
        self.assertEqual(saved["policy"], "bandit")
        self.assertNotIn("unknown", saved)

    def test_only_the_first_decision_counts(self):
        incident_id = incidents.open_incident(alert="ShopSLOFastBurn")
        approval_id = incidents.request_approval(incident_id, "restart_postgres", None, {}, 30)
        self.assertEqual(incidents.pending_approval()["id"], approval_id)
        incidents.decide(approval_id, True, "alice")
        with self.assertRaises(ValueError):
            incidents.decide(approval_id, False, "bob")
        incidents.expire(approval_id)  # no effect after a decision
        self.assertEqual(incidents.approval(approval_id)["decision"], "approved")
        self.assertIsNone(incidents.pending_approval())

    def test_expired_approval_cannot_be_approved_later(self):
        incident_id = incidents.open_incident(alert="ShopSLOFastBurn")
        approval_id = incidents.request_approval(incident_id, "restart_postgres", None, {}, 30)
        incidents.expire(approval_id)
        with self.assertRaises(ValueError):
            incidents.decide(approval_id, True, "alice")

    def test_scorecard_matches_faults_to_incidents(self):
        incidents.record_chaos("redis_down", "drill")
        incident_id = incidents.open_incident(alert="ShopSLOFastBurn")
        incidents.update_incident(incident_id, status="resolved", recovered=1, mitigation_s=5.0)
        card = incidents.scorecard()
        self.assertEqual((card["faults"], card["caught"], card["healed"]), (1, 1, 1))
        self.assertEqual(card["matches"][0]["incident_id"], incident_id)

    def test_active_chaos_is_cleared_by_a_reset(self):
        incidents.record_chaos("api_crash", "manual")
        self.assertEqual(incidents.active_chaos()["scenario"], "api_crash")
        incidents.clear_chaos()
        self.assertIsNone(incidents.active_chaos())


if __name__ == "__main__":
    unittest.main()
