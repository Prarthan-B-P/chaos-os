"""LLM agent with tools: gpt-4o-mini investigates before it acts.

The plain `llm` policy picks an action from eight symptom numbers. This agent
gets the same symptoms and the same description of the shop, plus read-only
tools an on-call engineer would reach for: PromQL queries, recent container
logs, container states and the readiness check. It must finish by calling
`decide`. Every tool call and its result is kept as an investigation trail,
so each decision can be audited afterwards.

The fault-injection layer (Toxiproxy) is deliberately out of reach: no tool
shows it, so the agent diagnoses from symptoms like a human would.
"""
import json
import re
import subprocess

import httpx

from . import lab, llm
from .actions import ACTIONS
from .config import API_URL, LAB_PROJECT, PROMETHEUS_URL

SERVICES = ("api", "redis", "postgres", "frontend")  # the shop, not the lab's tooling
MIN_TOOL_CALLS = 1  # always look before acting: `decide` is not offered on the first turn
MAX_TOOL_CALLS = 5
RESULT_CHARS = 1500  # per tool result sent back to the model
REMEDIATIONS = [a for a in ACTIONS if a != "none"]

SYSTEM = (
    "You are an on-call SRE remediation agent for a web shop: an API that reads "
    "items through a Redis cache backed by PostgreSQL. The service is failing its SLO "
    "right now (a request is good when it succeeds within 300 ms). You get live "
    "symptoms and read-only tools. Investigate efficiently (usually 2-4 tool calls), "
    "form a hypothesis about the root cause, then call `decide` with exactly ONE next "
    "recovery action from the allowed list, or give_up if none can help. Do not repeat "
    "actions already executed; if earlier actions did not heal the service, work out why."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "promql",
        "description": (
            "Instant PromQL query against the lab's Prometheus (5 s scrapes). Metrics: "
            "api_requests_total{endpoint,status}, api_request_duration_seconds_bucket{endpoint,le}, "
            "api_cache_total{result=hit|miss|error}, api_dependency_up{dependency=redis|postgres}, "
            "api_cache_bypass_enabled, shop_synthetic_requests_total{result=good|slow|error}, "
            "slo:bad_ratio:rate20s, slo:bad_ratio:rate1m."),
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "logs",
        "description": "Recent lines (last 2 minutes) of a service's container log, repeats collapsed.",
        "parameters": {"type": "object", "properties": {
            "service": {"type": "string", "enum": list(SERVICES)},
            "lines": {"type": "integer", "minimum": 5, "maximum": 60}},
            "required": ["service"]}}},
    {"type": "function", "function": {
        "name": "containers",
        "description": "State of the shop's containers: running or exited, uptime, health.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "readiness",
        "description": ("The API's /ready check: whether Redis and Postgres answer, their probe "
                        "latency in ms, and whether cache bypass is on."),
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "decide",
        "description": "Finish the investigation: choose ONE next action, or give_up.",
        "parameters": {"type": "object", "properties": {
            "hypothesis": {"type": "string", "description": "most likely root cause, one sentence"},
            "action": {"type": "string", "enum": [*REMEDIATIONS, "give_up"]},
            "reason": {"type": "string", "description": "why this action, one sentence"}},
            "required": ["hypothesis", "action", "reason"]}}},
]
INVESTIGATE = [t for t in TOOLS if t["function"]["name"] != "decide"]


# ------------------------------------------------------------------- tools

def _promql(query: str) -> str:
    try:
        body = httpx.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=3).json()
    except (httpx.HTTPError, ValueError) as exc:
        return f"error: Prometheus unreachable ({exc.__class__.__name__})"
    if body.get("status") != "success":
        return f"error: {body.get('error', 'query failed')}"
    series = body["data"]["result"]
    if not isinstance(series, list):  # scalar or string result
        return json.dumps(series)
    rows = [{"labels": {k: v for k, v in s["metric"].items() if k != "__name__"},
             "value": round(float(s["value"][1]), 4) if s["value"][1] not in ("NaN", "+Inf", "-Inf")
             else s["value"][1]} for s in series[:15]]
    more = f" (+{len(series) - 15} more series)" if len(series) > 15 else ""
    return (json.dumps(rows) + more) if rows else "no data"


def _collapse(lines: list[str]) -> list[str]:
    """Group lines that differ only in numbers (item ids, ports, timings)."""
    groups: dict[str, list] = {}
    for line in lines:
        key = re.sub(r"\d+", "#", line)
        groups.setdefault(key, [line, 0])[1] += 1
    return [line if n == 1 else f"{line}  (x{n} similar)" for line, n in groups.values()]


def _logs(service: str, lines: int = 30) -> str:
    if service not in SERVICES:
        return f"error: unknown service (choose from {', '.join(SERVICES)})"
    ids = lab.containers(service)
    if not ids:
        return f"no {service} container exists"
    try:
        out = subprocess.run(["docker", "logs", "--since", "2m", "--tail", str(min(int(lines), 60)),
                              ids[0]], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return "error: docker logs timed out"
    text = "\n".join(_collapse((out.stdout + out.stderr).strip().splitlines()))
    return text or "(no log lines in the last 2 minutes)"


def _containers() -> str:
    lines = lab.docker("ps", "-a", "--filter", f"label=com.docker.compose.project={LAB_PROJECT}",
                       "--filter", "label=com.docker.compose.oneoff=False", "--format",
                       '{{.Label "com.docker.compose.service"}}: {{.State}} ({{.Status}})').splitlines()
    return "\n".join(sorted(line for line in lines if line.split(":")[0] in SERVICES))


def _readiness() -> str:
    try:
        response = httpx.get(f"{API_URL}/ready", timeout=5)
    except httpx.HTTPError as exc:
        return f"the API did not answer ({exc.__class__.__name__})"
    return f"HTTP {response.status_code}: {response.text}"


def run_tool(name: str, args: dict) -> str:
    try:
        if name == "promql":
            return _promql(str(args.get("query", "")))
        if name == "logs":
            return _logs(str(args.get("service", "")), args.get("lines", 30))
        if name == "containers":
            return _containers()
        if name == "readiness":
            return _readiness()
    except Exception as exc:  # a broken tool is information too; never crash the policy
        return f"error: {exc.__class__.__name__}: {exc}"
    return f"error: unknown tool '{name}'"


# ------------------------------------------------------------------ policy

class AgentPolicy:
    """LLM agent (gpt-4o-mini) that investigates with read-only tools, then acts."""

    name = "llm_agent"
    SYSTEM = SYSTEM

    def __init__(self):
        if not llm.available():
            raise RuntimeError("OPENAI_API_KEY is not set (add it to .env)")
        self.last_reason: str | None = None
        self.last_trail: list[dict] = []

    def choose(self, s: dict, executed: list[str], rejected: list[str]) -> str | None:
        messages = [{"role": "system", "content": self.SYSTEM}, {"role": "user", "content": json.dumps({
            "symptoms": s,
            "allowed_actions": {a: ACTIONS[a].description for a in REMEDIATIONS},
            "already_executed": executed,
            "rejected_by_safety_validator": rejected,
        })}]
        trail: list[dict] = []
        self.last_reason, self.last_trail = None, trail
        for turn in range(MAX_TOOL_CALLS + 1):
            # Out of investigation budget: the next call must be the decision.
            force = {"type": "function", "function": {"name": "decide"}}
            tools = INVESTIGATE if turn < MIN_TOOL_CALLS else TOOLS
            try:
                reply = llm.chat_tools(messages, tools, force if turn == MAX_TOOL_CALLS else "required")
            except RuntimeError as exc:
                print(f"  llm_agent: {exc}; giving up", flush=True)
                return None
            calls = reply.get("tool_calls") or []
            if not calls:
                return None
            messages.append({"role": "assistant", "content": reply.get("content"), "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                if name == "decide":
                    self.last_reason = f"{args.get('hypothesis', '')} -> {args.get('reason', '')}".strip(" ->")
                    action = args.get("action")
                    return None if action in (None, "", "give_up") else str(action)
                result = run_tool(name, args)
                trail.append({"tool": name, "args": args, "result": result[:400]})
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": result[:RESULT_CHARS]})
        return None
