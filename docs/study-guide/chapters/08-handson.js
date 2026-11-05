// Chapter 8: hands-on: run, reproduce, troubleshoot.
module.exports = (h) => [
  h.H1("8. Hands-on: running and reproducing everything"),
  h.Lead("Every command below was run while building the project. Use PowerShell or Git Bash from the project " +
    "folder, with Docker Desktop running."),

  h.H2("8.1 Start the lab"),
  ...h.code([
    "docker compose up -d --build --wait      # the lab + dashboard + on-call agent (first build: minutes)",
    "python scripts/smoke_test.py             # should print PASS",
  ]),
  h.table(["Open", "Address"], [
    ["Evidence dashboard", "http://localhost:8090"],
    ["Shop", "http://localhost:8080"],
    ["Grafana (Service Health)", "http://localhost:3000  (admin / admin)"],
    ["Prometheus", "http://localhost:9090"],
    ["Alertmanager", "http://localhost:9093"],
    ["API docs", "http://localhost:8000/docs"],
    ["Jenkins", "http://localhost:8081  (start it with: docker compose -f jenkins/docker-compose.yml up -d)"],
  ], [2, 5]),
  h.spacer(),
  ...h.callout("warn", "Never run `docker compose down -v` unless you mean it", [
    "`-v` deletes the volumes, including the experiment history (every trial, incident and the trained bandit). " +
    "Plain `docker compose down` is safe.",
  ]),

  h.H2("8.2 Run experiments from the command line"),
  ...h.code([
    "# One failure, one responder",
    "docker compose run --rm controller run --scenario redis_latency --policy bandit",
    "# The fixed-action matrix (training data for the bandit)",
    "docker compose run --rm controller run --scenario all --action restart_redis,restart_postgres,restart_api,cache_bypass,warm_cache --reps 2 --timeout 30",
    "# Train the bandit and see its learning curve",
    "docker compose run --rm controller train",
    "docker compose run --rm controller learning-curve",
    "# Compare responders, then the held-out generalisation test",
    "docker compose run --rm controller run --scenario all --policy rule_based,heuristic,bandit,llm --reps 2 --timeout 90",
    "docker compose run --rm controller run --scenario held_out --policy rule_based,heuristic,bandit,llm --reps 3 --timeout 90",
    "# The LLM ablation (2 x 2)",
    "docker compose run --rm controller run --scenario all --policy llm,llm_sre,llm_agent,llm_agent_sre --reps 2 --timeout 90",
    "# Red-team the safety validator",
    "docker compose run --rm controller run --scenario redis_down --policy adversarial",
    "# Summaries and AI write-ups",
    "docker compose run --rm controller report --by policy",
    "docker compose run --rm controller explain",
  ]),

  h.H2("8.3 On-call mode"),
  ...h.code([
    "# An unannounced drill: passes only if the agent heals it within 120 s",
    "docker compose run --rm controller drill --scenario redis_down --within 120",
    "# The full measurement campaign (all 7 failures, 3 times each, operator approves after 5 s)",
    "python scripts/oncall_campaign.py --reps 3 --policy heuristic --out oncall-campaign.json",
    "# Watch the agent think",
    "docker logs -f chaosos-oncall-1",
  ]),
  h.P("In the dashboard: **On-call** page → choose a failure → **Break it**. Approve or deny when the orange " +
    "approval card appears."),

  h.H2("8.4 CI, alert-rule tests and the security scan"),
  ...h.code([
    "docker compose run --rm --no-deps --entrypoint promtool prometheus test rules /etc/prometheus/tests/slo_test.yml",
    "docker compose run --rm --entrypoint python controller -m unittest discover -s tests -v",
    "sh scripts/security-scan.sh              # reports and SBOMs in security-reports/",
  ]),
  h.P("Jenkins builds every branch automatically within 5 minutes of a push (it polls GitHub). Open the " +
    "**chaos-os-ci** job to see the stage view and the archived reports."),

  h.H2("8.5 Regenerate the paper's figures and this guide"),
  ...h.code([
    "python docs/paper/make_figures.py --campaign oncall-campaign.json --drill-incident <id>",
    "cd docs/paper && tectonic -X compile chaos-os-ieee.tex",
    "cd docs/study-guide && node build.js",
  ]),

  h.H2("8.6 Share it online"),
  ...h.code([
    ".\\deploy\\share.ps1           # public HTTPS link from your laptop (Cloudflare tunnel), with login",
    ".\\deploy\\share.ps1 -Stop     # back to the normal local lab",
    ".\\deploy\\deploy.ps1 -Server <ip>   # full deployment to a cloud VM",
  ]),

  h.H2("8.7 Troubleshooting"),
  h.table(["Symptom", "Fix"], [
    ["\"the lab is busy\" when starting a run", "An experiment or an on-call incident owns the lab; wait (at most ~2 min)"],
    ["The top bar says fault active", "Dashboard → Overview → Reset lab"],
    ["Docker commands fail with \"cannot connect\"", "Start Docker Desktop and wait for \"Engine running\""],
    ["LLM policies show (unavailable)", "Put OPENAI_API_KEY in .env, then docker compose up -d"],
    ["Bandit shows (unavailable)", "Train it: docker compose run --rm controller train"],
    ["No page after Break it", "Check Prometheus targets (traffic must be up) and Alertmanager at :9093"],
    ["Port 8080 already in use", "Another program uses it; stop it or change the port in docker-compose.override.yml"],
  ], [3, 4]),
];
