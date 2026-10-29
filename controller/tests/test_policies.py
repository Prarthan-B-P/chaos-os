"""Policies and the bandit, on synthetic symptoms."""
import random
import unittest

from chaosctl import bandit
from chaosctl.policies import AdversarialPolicy, FixedPolicy, HeuristicPolicy, RuleBasedPolicy


def symptoms(api_up=True, redis_ok=True, postgres_ok=True, redis_ms=1.0, postgres_ms=1.0,
             error_rate=1.0, p95_ms=500.0):
    return {"api_up": api_up, "redis_ok": redis_ok, "postgres_ok": postgres_ok,
            "redis_ms": redis_ms, "postgres_ms": postgres_ms,
            "error_rate": error_rate, "p95_ms": p95_ms}


API_DOWN = symptoms(api_up=False, redis_ok=None, postgres_ok=None, redis_ms=None,
                    postgres_ms=None)
REDIS_DOWN = symptoms(redis_ok=False, redis_ms=3)
REDIS_SLOW = symptoms(redis_ok=False, redis_ms=505)
PG_SLOW = symptoms(postgres_ms=820, error_rate=0.5)
PG_DOWN = symptoms(postgres_ok=False, postgres_ms=2000)


class RulePolicyTests(unittest.TestCase):
    def test_rule_based_restarts_what_looks_broken_then_escalates(self):
        p = RuleBasedPolicy()
        self.assertEqual(p.choose(REDIS_SLOW, [], []), "restart_redis")
        self.assertEqual(p.choose(REDIS_SLOW, ["restart_redis"], []), "restart_api")
        self.assertEqual(p.choose(API_DOWN, [], []), "restart_api")
        self.assertIsNone(p.choose(API_DOWN, ["restart_api"], []))

    def test_heuristic_uses_measured_characteristics(self):
        p = HeuristicPolicy()
        self.assertEqual(p.choose(API_DOWN, [], []), "restart_api")
        self.assertEqual(p.choose(REDIS_DOWN, [], []), "cache_bypass")
        self.assertEqual(p.choose(REDIS_DOWN, ["cache_bypass"], []), "restart_redis")
        self.assertEqual(p.choose(PG_SLOW, [], []), "warm_cache")
        self.assertEqual(p.choose(PG_DOWN, [], []), "restart_postgres")

    def test_fixed_policy_acts_once(self):
        p = FixedPolicy("cache_bypass")
        self.assertEqual(p.choose(REDIS_DOWN, [], []), "cache_bypass")
        self.assertIsNone(p.choose(REDIS_DOWN, ["cache_bypass"], []))

    def test_adversarial_policy_eventually_stops(self):
        p = AdversarialPolicy()
        rejected = []
        while (proposal := p.choose(REDIS_DOWN, [], rejected)) is not None:
            rejected.append(proposal)
        self.assertEqual(rejected, AdversarialPolicy.PROPOSALS)


class BanditTests(unittest.TestCase):
    def test_features_hide_nothing_but_the_fault_name(self):
        x = bandit.features(API_DOWN)
        self.assertEqual(len(x), len(bandit.FEATURES))
        self.assertEqual(x[bandit.FEATURES.index("api_down")], 1.0)

    def test_learns_the_right_action_per_context(self):
        best = {"api": "restart_api", "rdown": "cache_bypass", "rslow": "cache_bypass",
                "pslow": "warm_cache", "pdown": "restart_postgres"}
        contexts = {"api": API_DOWN, "rdown": REDIS_DOWN, "rslow": REDIS_SLOW,
                    "pslow": PG_SLOW, "pdown": PG_DOWN}
        actions = ["restart_api", "cache_bypass", "warm_cache", "restart_postgres",
                   "restart_redis"]
        rng = random.Random(1)
        logged = []
        for _ in range(4):
            for name, sym in contexts.items():
                for a in actions:
                    reward = 0.9 if a == best[name] else 0.0
                    logged.append((sym, a, reward + rng.uniform(-0.05, 0.05)))
        model = bandit.fit(logged, actions)
        for name, sym in contexts.items():
            self.assertEqual(model.choose(bandit.features(sym)), best[name], name)

    def test_model_round_trips_through_json(self):
        model = bandit.fit([(REDIS_DOWN, "cache_bypass", 1.0)], ["cache_bypass", "restart_api"])
        clone = bandit.LinUCB.from_json(model.to_json())
        x = bandit.features(REDIS_DOWN)
        self.assertEqual(model.scores(x, True), clone.scores(x, True))

    def test_choose_respects_exclusions(self):
        model = bandit.fit([(REDIS_DOWN, "cache_bypass", 1.0)], ["cache_bypass", "restart_api"])
        self.assertEqual(model.choose(bandit.features(REDIS_DOWN), exclude=["cache_bypass"]),
                         "restart_api")


if __name__ == "__main__":
    unittest.main()
