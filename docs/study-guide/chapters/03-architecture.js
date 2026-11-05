// Chapter 3: architecture, every service, data flows, where things live.
const path = require("path");
const FIG = (f) => path.join(__dirname, "..", "..", "paper", "figures", f);

module.exports = (h) => [
  h.H1("3. Architecture: every part and why it exists"),
  h.Lead("CHAOS OS has three layers: the **system under test** (a small online shop), the **observability and " +
    "response** layer (metrics, alerts, the on-call agent), and the **control, safety and evidence** layer " +
    "(experiments, policies, the safety validator, Ansible, results, the dashboard and gpt-4o-mini)."),
  ...h.figure(FIG("architecture.png"), "CHAOS OS architecture. Orange boxes are where faults and fixes enter " +
    "the system; the purple box is the only part that talks to OpenAI. Faults are also injected from the " +
    "dashboard's Break-it button and the chaos monkey.", 6.4),

  h.H2("3.1 The system under test: a three-tier web shop"),
  h.P("The shop is deliberately simple so that every failure is understandable: a product catalogue of 1,000 " +
    "items, read through a **cache-aside** pattern."),
  ...h.numbered([
    "A request `GET /items/{id}` reaches the **API** (FastAPI, Python).",
    "The API first asks **Redis** (the cache). Hit: answer immediately (about 1-2 ms).",
    "Miss: the API reads **PostgreSQL** (the source of truth), stores the item in Redis for 60 s, and answers.",
    "If Redis errors (down or slower than its 500 ms timeout), the API returns **503** unless **cache bypass** is " +
    "on, in which case every read goes straight to Postgres.",
    "If Postgres errors or its connection pool (10 connections, 2 s timeout) is exhausted, the API returns 503.",
  ]),
  h.P("Important: the API reaches Redis and Postgres **through Toxiproxy**. That lets us add latency or cut the " +
    "network without touching Redis or Postgres themselves, exactly like a real network problem."),

  h.H2("3.2 Every container"),
  h.table(["Service", "Technology", "What it does", "Why we need it"], [
    ["frontend", "nginx (unprivileged, port 8080)", "Serves the shop page; proxies /api/ to the API", "A realistic entry point; the smoke test goes through it"],
    ["api", "FastAPI + uvicorn, Python 3.12", "Shop logic: /items, /health, /ready, /metrics, admin endpoints for fixes", "The service whose recovery we measure"],
    ["redis", "Redis 7.2", "Cache with 60 s TTL", "Cache failures are common and subtle"],
    ["postgres", "PostgreSQL 16", "Item database (1,000 rows)", "Source of truth; slow or dead DB is a classic incident"],
    ["toxiproxy", "Shopify Toxiproxy 2.9", "Network proxy for Redis and Postgres", "Injects latency and partitions"],
    ["traffic", "Python, httpx, prometheus-client", "Synthetic users: 2 req/s; counts good / slow / error", "The SLI the alerts are built on"],
    ["prometheus", "Prometheus 2.53", "Scrapes metrics every 5 s; SLO recording + alert rules", "Monitoring and alerting brain"],
    ["alertmanager", "Alertmanager 0.27", "Routes pages to the agent's webhook", "Production-style alert routing"],
    ["grafana", "Grafana 11.1", "Service-health and SLO dashboards with annotations", "Visual evidence"],
    ["oncall", "chaosctl (Python) in the controller image", "The on-call agent: webhook receiver + remediation", "Heals unannounced failures"],
    ["dashboard", "React 18 + Vite 6 + Recharts; FastAPI", "Evidence dashboard, approvals, chaos controls, gen AI", "Shows everything; human-in-the-loop"],
    ["controller (tool)", "chaosctl CLI", "Runs experiments, training, reports, gate, drill", "The experiment engine"],
    ["ansible (tool)", "ansible-core 2.21.6", "Runs recovery playbooks", "Infrastructure as code for fixes"],
    ["jenkins (separate)", "Jenkins LTS + Docker CLI", "CI/CD pipeline", "Gates every release"],
  ], [1.3, 2, 2.6, 2.4]),
  h.spacer(),

  h.H2("3.3 The three main data flows"),
  h.H3("Flow A: an experiment (we know what we broke)"),
  h.P("The **controller** resets the lab, sends 20 requests per second, injects a fault, detects the outage from " +
    "its own traffic, asks a **policy** for an action, checks it with the **safety validator**, runs it with " +
    "**Ansible**, waits up to 20 s for healing, repeats if needed (at most 3 actions), measures recovery, and " +
    "saves the trial and every step to **SQLite**."),
  h.H3("Flow B: on-call (nobody tells the agent anything)"),
  h.P("The **synthetic users** see errors, **Prometheus** sees the SLO burning, **Alertmanager** sends a webhook, " +
    "the **on-call agent** confirms with its own probe traffic, runs the same remediation loop (with a human " +
    "approval step for high-impact actions), records an **incident**, and asks gpt-4o-mini for a post-mortem."),
  h.H3("Flow C: a release (Jenkins)"),
  h.P("Jenkins builds all images, runs unit tests and alert-rule tests, scans for secrets and vulnerabilities, " +
    "starts an isolated lab, runs a smoke test, runs the **resilience gate** (6 real faults with deadlines) and " +
    "the **on-call drill**, archives the reports, and tears the lab down."),

  h.H2("3.4 Where things live in the repository"),
  h.table(["Path", "Contents"], [
    ["app/api, app/frontend, app/db", "The shop: API code, nginx config + page, database schema and seed data"],
    ["app/traffic", "Synthetic users (SLI)"],
    ["chaos/toxiproxy", "Toxiproxy proxy definitions (redis, postgres)"],
    ["controller/chaosctl", "The brain: load generator, analysis, experiments, safety, policies, bandit, LLM, agent, on-call, incidents, CLI"],
    ["controller/tests", "45 unit tests"],
    ["ansible/playbooks", "Recovery actions: restart_service, set_cache_bypass, warm_cache"],
    ["observability/prometheus", "Scrape config, SLO rules (rules/slo.yml) and their unit tests (tests/slo_test.yml)"],
    ["observability/alertmanager", "Routing to the agent; inhibition of tickets during pages"],
    ["observability/grafana", "Provisioned data source and dashboards"],
    ["dashboard/server, dashboard/web", "Dashboard back end (FastAPI) and front end (React)"],
    ["safety-policy.yml", "The safety rules (policy as code)"],
    ["resilience-gate.yml", "The CI resilience checks and deadlines (policy as code)"],
    ["Jenkinsfile, jenkins/", "The pipeline and the Jenkins image with the job defined as code"],
    ["scripts/", "Smoke test, security scan, on-call measurement campaign"],
    ["deploy/", "Production overlay (Caddy), Ansible server provisioning, laptop sharing tunnel"],
    ["docs/", "Demo runbook, this guide, the IEEE paper and its figure generator"],
  ], [2.2, 5]),
];
