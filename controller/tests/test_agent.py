"""The tool-using LLM agent, with a scripted model (no network, no OpenAI calls)."""
import json
import os
import unittest
from unittest import mock

from chaosctl import agent

SYMPTOMS = {"error_rate": 1.0, "p95_ms": 500, "api_up": True, "redis_ok": False,
            "postgres_ok": True, "redis_ms": 3.0, "postgres_ms": 2.0}


def call(name, args=None, call_id="c1"):
    return {"tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args or {})}}]}


class ScriptedModel:
    """Returns the scripted replies in order; records what it was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.tool_choices = []
        self.offered = []

    def __call__(self, messages, tools, tool_choice="required", max_tokens=400):
        self.tool_choices.append(tool_choice)
        self.offered.append([t["function"]["name"] for t in tools])
        return self.replies.pop(0)


class AgentTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
        env.start()
        self.addCleanup(env.stop)

    def choose(self, model, tool_results=None):
        with mock.patch.object(agent.llm, "chat_tools", model), \
                mock.patch.object(agent, "run_tool", lambda name, args: (tool_results or {}).get(name, "ok")):
            policy = agent.AgentPolicy()
            return policy, policy.choose(SYMPTOMS, [], [])

    def test_investigates_then_decides(self):
        model = ScriptedModel(
            call("readiness"),
            call("decide", {"hypothesis": "Redis is unreachable", "action": "cache_bypass",
                            "reason": "serve from Postgres until Redis is back"}))
        policy, action = self.choose(model, {"readiness": 'HTTP 503: {"redis": false}'})
        self.assertEqual(action, "cache_bypass")
        self.assertEqual([t["tool"] for t in policy.last_trail], ["readiness"])
        self.assertIn("redis", policy.last_trail[0]["result"])
        self.assertIn("Redis is unreachable", policy.last_reason)
        self.assertNotIn("decide", model.offered[0])  # must look before acting
        self.assertIn("decide", model.offered[1])

    def test_investigation_budget_forces_a_decision(self):
        model = ScriptedModel(*[call("containers", call_id=f"c{i}") for i in range(agent.MAX_TOOL_CALLS)],
                              call("decide", {"hypothesis": "h", "action": "restart_api", "reason": "r"}))
        policy, action = self.choose(model)
        self.assertEqual(action, "restart_api")
        self.assertEqual(len(policy.last_trail), agent.MAX_TOOL_CALLS)
        self.assertEqual(model.tool_choices[-1], {"type": "function", "function": {"name": "decide"}})
        self.assertTrue(all(c == "required" for c in model.tool_choices[:-1]))

    def test_give_up_returns_none(self):
        _, action = self.choose(ScriptedModel(
            call("containers"),
            call("decide", {"hypothesis": "h", "action": "give_up", "reason": "nothing helps"})))
        self.assertIsNone(action)

    def test_model_failure_gives_up_safely(self):
        def broken(*_args, **_kwargs):
            raise RuntimeError("OpenAI request failed: ConnectTimeout")
        _, action = self.choose(broken)
        self.assertIsNone(action)


class ToolTests(unittest.TestCase):
    def test_logs_only_for_shop_services(self):
        self.assertIn("unknown service", agent.run_tool("logs", {"service": "toxiproxy"}))

    def test_unknown_tool_is_reported_not_raised(self):
        self.assertIn("unknown tool", agent.run_tool("drop_database", {}))

    def test_broken_tool_becomes_information(self):
        with mock.patch.object(agent, "_containers", side_effect=OSError("docker not found")):
            self.assertIn("docker not found", agent.run_tool("containers", {}))

    def test_repeated_log_lines_are_collapsed(self):
        lines = [f'INFO: 172.18.0.5:{4000 + i} - "GET /items/{i} HTTP/1.1" 503' for i in range(40)]
        out = agent._collapse(lines + ["Application startup complete."])
        self.assertEqual(len(out), 2)
        self.assertIn("x40 similar", out[0])


if __name__ == "__main__":
    unittest.main()
