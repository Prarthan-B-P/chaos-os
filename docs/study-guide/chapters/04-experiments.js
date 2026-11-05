// Chapter 4: experiments, the recovery definition, failures, actions, safety.
module.exports = (h) => [
  h.H1("4. How an experiment works"),
  h.Lead("Every trial is a small, fully measured incident. The controller plays both the attacker (it injects " +
    "the fault) and the on-call engineer (it runs the chosen responder), and records everything."),

  h.H2("4.1 The life of one trial"),
  ...h.numbered([
    "**Reset** the lab to a known-good state: remove all Toxiproxy faults, start any stopped container, wait " +
    "for `/ready`, switch cache bypass off, and flush Redis (every trial starts with a cold cache).",
    "**Warm up** for 15 s at 20 requests/s. The 10 s before injection are the **baseline**; if the baseline is " +
    "not healthy the trial is marked _invalid_ and excluded.",
    "**Inject** the fault.",
    "**Detect** the outage from live traffic (the last 1-second window is unhealthy). If nothing breaks within " +
    "15 s, the fault had no impact.",
    "**Remediation loop** (at most 3 executed actions): observe symptoms, ask the policy, check with the safety " +
    "validator, run the Ansible playbook, wait up to 20 s for 3 healthy seconds. If it healed, stop; otherwise " +
    "observe again and ask for the next action.",
    "**Keep the load running** until recovery is confirmed or the timeout (60 s, 90 s for policy runs) expires.",
    "**Reset** again and **save** the trial and every step (symptoms, action, verdict, timing, reward, the " +
    "LLM's reason, the agent's investigation trail) to SQLite.",
  ]),
  ...h.callout("remember", "The load generator is \"open model\"", [
    "It sends a request every 50 ms no matter how slow the answers are. A closed-model generator (wait for an " +
    "answer before sending the next) would quietly send less traffic during an outage and hide the damage.",
  ]),

  h.H2("4.2 Symptoms: what a policy is allowed to see"),
  h.P("Policies never see the name of the injected fault. They see only what an operator could observe:"),
  h.table(["Symptom", "Source", "Example during redis_latency"], [
    ["error_rate", "load generator, last 1 s", "1.00 (every request failing)"],
    ["p95_ms", "load generator, last 1 s", "505 ms"],
    ["api_up", "API /ready answers?", "true"],
    ["redis_ok, redis_ms", "/ready pings Redis", "false, 501 ms (the 500 ms timeout)"],
    ["postgres_ok, postgres_ms", "/ready runs SELECT 1", "true, 1.4 ms"],
  ], [2, 2.4, 2.6]),
  h.spacer(),

  h.H2("4.3 The recovery definition (be precise about this)"),
  h.P("Prometheus scrapes every 5 s, which is too coarse to measure recoveries of 1-2 s. So the load generator " +
    "times every single request (timeout 2 s) and `controller/chaosctl/analysis.py` (unit-tested) decides:"),
  ...h.bullets([
    "Time after injection is cut into **1-second windows** by request send time.",
    "A window is **healthy** when at least **99%** of its requests succeed and its **p95 latency is at most 300 ms**.",
    "The service has **recovered** once **5 consecutive healthy windows** follow the first unhealthy one.",
    "The **recovery time** is pinned below window resolution: the send time of the first request after the " +
    "last bad request (failed or slower than 300 ms) before that healthy run.",
  ]),
  ...h.callout("explain", "Worked example", [
    "Fault at t = 0. Requests fail from 0.05 s. The policy runs cache_bypass at 1.2 s; the last failing " +
    "request was sent at 1.75 s; every window from 2 s to 7 s is healthy. Recovery time = send time of the " +
    "first request after 1.75 s, i.e. 1.80 s. That is the 1.8 s you see for redis_down + cache_bypass.",
  ]),

  h.H2("4.4 The seven failures"),
  h.table(["Failure", "How we inject it", "What users see", "Set"], [
    ["redis_down", "docker kill the Redis container", "503 errors (cache unavailable)", "training"],
    ["redis_latency", "Toxiproxy adds 800 ms to Redis traffic (> the 500 ms timeout)", "503 errors although Redis is running", "training"],
    ["postgres_latency", "Toxiproxy adds 400 ms to Postgres traffic", "Slow responses on every cache miss; pool exhaustion", "training"],
    ["postgres_down", "docker kill the Postgres container", "503 errors (database unavailable)", "training"],
    ["api_crash", "docker kill the API container", "Connection errors", "training"],
    ["redis_partition", "Toxiproxy disables the Redis proxy (container healthy)", "Looks exactly like redis_down", "held out"],
    ["redis_down_slow_db", "Kill Redis and add 400 ms to Postgres", "Errors, then slowness", "held out"],
  ], [1.6, 2.8, 2.3, 0.9]),
  h.spacer(),

  h.H2("4.5 The six recovery actions (Ansible playbooks)"),
  h.table(["Action", "What it does", "Impact / cost", "When it helps"], [
    ["none", "Nothing (baseline)", "none / 0.00", "Never, but it measures the fault's natural behaviour"],
    ["restart_redis", "docker restart Redis, wait for /ready", "medium / 0.05", "Redis process crashed"],
    ["restart_postgres", "docker restart Postgres, wait for /ready", "high / 0.20", "Postgres process crashed"],
    ["restart_api", "docker restart the API, wait for /ready", "medium / 0.10", "API process crashed"],
    ["cache_bypass", "API serves reads from Postgres, skipping Redis", "low / 0.05", "Redis dead, slow or unreachable"],
    ["warm_cache", "Load all 1,000 items into Redis (TTL 10 min) with one query", "low / 0.02", "Slow database: hits avoid it"],
  ], [1.4, 2.9, 1.3, 2.3]),
  h.spacer(),
  h.P("**Why each fix works (or not)** is the heart of the first result:"),
  ...h.bullets([
    "**redis_latency:** restarting Redis cannot help: Redis is fine, the network to it is slow. Only bypassing " +
    "the cache helps. This is exactly where a classic runbook fails.",
    "**postgres_latency:** bypassing the cache makes it worse (every read now hits the slow database). Warming " +
    "the cache in one bulk query puts every item in Redis, so requests stop touching the slow database.",
    "**redis_partition (held out):** looks like a dead Redis, but the container is healthy, so a restart does " +
    "nothing. Cache bypass works.",
    "**redis_down_slow_db (held out):** cache bypass is a trap (all load goes to the slow database). The right " +
    "fix needs two coordinated steps: restart Redis, then warm the cache. No policy found this.",
  ]),

  h.H2("4.6 The safety validator"),
  h.P("`controller/chaosctl/safety.py` checks every proposal, from every policy, in this order. The first rule " +
    "that fails blocks the action and the reason is recorded:"),
  ...h.numbered([
    "**Approved environment only:** the Compose project must match `chaosos` or `chaosos-ci-*`.",
    "**Allowlist:** the action must exist in `safety-policy.yml` and in the code. `drop_database` does not.",
    "**No repeats:** an action may run once per incident (stops restart loops, a classic automation disaster).",
    "**Budget:** at most 3 executed actions per incident.",
    "**Approval for high impact:** `restart_postgres` is high impact. In experiments the isolated lab " +
    "auto-approves it (logged); in on-call mode a human decides in the dashboard (no answer in 60 s = not run); " +
    "`deny` mode always blocks it.",
  ]),
  h.P("A second, independent layer: the Ansible playbooks refuse any service outside `allowed_services` " +
    "(api, redis, postgres, frontend), so even a bug in the validator could not restart Grafana or Jenkins."),
  ...h.callout("explain", "The red-team test", [
    "The adversarial policy proposes `drop_database`, `restart_grafana`, repeated restarts and a high-impact " +
    "action on purpose. In every run, the unsafe proposals were blocked with a clear reason and only allowlisted " +
    "actions ran. Across all experiments, **zero unsafe actions executed**.",
  ]),
];
