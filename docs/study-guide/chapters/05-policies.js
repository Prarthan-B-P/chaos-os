// Chapter 5: the responders (policies), the bandit, the LLM and the agent.
module.exports = (h, R) => {
  const lc = R.learning_curve || {};
  const last = (lc.curve || []).slice(-1)[0] || {};
  return [
    h.H1("5. The responders: who decides what to do"),
    h.Lead("A policy receives the symptoms plus what has already been tried in this incident, and proposes the " +
      "next action. Every policy gets exactly the same inputs, and every proposal goes through the same safety " +
      "validator. Code: `controller/chaosctl/policies.py`, `bandit.py`, `llm.py`, `agent.py`."),

    h.H2("5.1 Rule-based runbook (the classic approach)"),
    h.P("\"Restart whatever looks broken, then restart the app.\" If the API is down, restart the API; if Redis " +
      "looks broken, restart Redis; if Postgres looks broken, restart Postgres; finally restart the API. This is " +
      "what many teams do, and it is our baseline."),

    h.H2("5.2 Expert heuristic (hand-written rules)"),
    h.P("Rules written after studying the training results: API down → restart API; Postgres unreachable → " +
      "restart Postgres; Redis unreachable → cache bypass (then restart Redis); Postgres probe slower than " +
      "200 ms → warm cache; Redis probe slower than 200 ms → cache bypass. It is strong precisely because a " +
      "human encoded the answers; that is also its weakness (someone must study every new failure)."),

    h.H2("5.3 LinUCB contextual bandit (machine learning)"),
    h.P("**Features (8):** a bias term, API down, Redis unreachable, Postgres unreachable, Redis probe latency, " +
      "Postgres probe latency, error rate, and p95 latency. Latencies are log-scaled into 0-1 (2 s and above " +
      "saturate), so 500 ms and 2,000 ms are distinguishable but extreme values do not dominate."),
    h.P("**Reward** for each executed step: `max(0, 1 - time_to_heal / 20 s) - safety_cost(action)`. A step that " +
      "heals the service immediately scores close to 1; one that never heals scores 0; risky actions pay a " +
      "penalty (restart_postgres 0.20, restart_api 0.10, restart_redis and cache_bypass 0.05, warm_cache 0.02)."),
    h.P("**Model:** for each action a, LinUCB keeps a matrix A_a (identity plus the sum of x·xᵀ) and a vector " +
      "b_a (the sum of reward·x). The predicted reward is θ_a·x with θ_a = A_a⁻¹·b_a, and the uncertainty bonus " +
      "is α·√(xᵀA_a⁻¹x) with α = 0.5. At decision time the lab picks the highest prediction among actions not " +
      "yet tried in the incident."),
    h.P(`**Training:** offline, from logged steps of the **training failures only** (the code asserts that no ` +
      `held-out data leaks in). The learning curve replays the ${lc.steps ?? "logged"} logged steps in 30 random ` +
      `orders and scores how often the bandit picks the best measured action: it ends at ` +
      `${h.pct(last.accuracy)}.`),
    ...h.callout("question", "\"Isn't the bandit just memorising failure names?\"", [
      "No. It never sees the name. It sees 8 symptom numbers. The proof is the held-out Redis partition: never " +
      "trained on, it looks like \"Redis unreachable\", and the bandit chose cache bypass (3/3 recovered in 0.8 s) " +
      "while the runbook restarted a healthy container and failed 0/3.",
    ]),

    h.H2("5.4 LLM policy (gpt-4o-mini)"),
    h.P("The symptoms, the allowed actions with their descriptions, and what was already executed or blocked are " +
      "sent as JSON. The system prompt is short:"),
    ...h.code([
      "You are an on-call SRE remediation agent for a web shop: an API that reads items",
      "through a Redis cache backed by PostgreSQL. You receive live symptoms and must pick",
      "exactly ONE next recovery action from the allowed list, or \"give_up\" if none can help.",
      "Do not repeat actions already executed.",
      "Reply with JSON only: {\"action\": \"<name>\", \"reason\": \"<one sentence>\"}",
    ]),
    h.P("Temperature 0 (as repeatable as possible), JSON mode, and the model's reason is stored with each step. " +
      "The API key lives only in the git-ignored `.env` and is never printed or logged."),

    h.H2("5.5 LLM agent with tools (agentic AI)"),
    h.P("The agent gets the same prompt and inputs **plus five tools**. It must call at least one investigation " +
      "tool before it may decide (\"look before you act\"), and at most five before it is forced to decide:"),
    h.table(["Tool", "What it returns", "Safety"], [
      ["promql(query)", "Any instant Prometheus query: error counters, cache hits/misses, dependency up, SLO ratios", "Read-only"],
      ["logs(service)", "Last 2 minutes of a shop container's log, repeated lines collapsed", "Only api, redis, postgres, frontend"],
      ["containers()", "Running / exited state and health of the shop containers", "Read-only"],
      ["readiness()", "The API's /ready result: Redis/Postgres reachable, probe ms, cache bypass flag", "Read-only"],
      ["decide(hypothesis, action, reason)", "Ends the investigation with one action or give_up", "Still checked by the validator"],
    ], [1.8, 3.6, 1.8]),
    h.spacer(),
    h.P("Toxiproxy (the fault injector) is deliberately invisible to every tool, so the agent cannot cheat by " +
      "reading the fault. Every tool call and its result is saved as an **investigation trail**, shown in the " +
      "dashboard under each step."),

    h.H2("5.6 The ablation variants"),
    h.P("To learn _why_ the LLM behaves as it does, we added one paragraph of **generic SRE guidance** (no " +
      "failure-specific rules) and tested a 2 x 2 design: {no tools, tools} x {no guidance, guidance}:"),
    ...h.code([
      "SRE practice: a restart only helps when the process itself has crashed or hung; it does",
      "not fix a slow or unreachable network, and it throws away warm state. Check whether a",
      "component is down or merely slow before restarting it. Prefer the least disruptive action",
      "that restores user traffic, and think through each action's side effects on the other",
      "components.",
    ]),
    h.table(["Variant", "Tools", "Guidance", "Name in the code"], [
      ["LLM", "no", "no", "llm"],
      ["LLM + SRE guidance", "no", "yes", "llm_sre"],
      ["LLM agent + tools", "yes", "no", "llm_agent"],
      ["Agent + tools + guidance", "yes", "yes", "llm_agent_sre"],
    ], [2.6, 1, 1, 2]),
    h.spacer(),
    ...h.callout("remember", "Why an ablation?", [
      "If we only compared \"LLM\" with \"agent + guidance\" and the second won, we could not say whether the " +
      "tools or the guidance caused it. Changing one factor at a time isolates each effect. That is what makes " +
      "it research rather than a demo.",
    ]),

    h.H2("5.7 Adversarial (red-team) policy"),
    h.P("It exists only to attack the safety validator: it proposes `drop_database`, `restart_grafana`, repeated " +
      "restarts and high-impact actions on purpose. It is never used to fix anything."),
  ];
};
