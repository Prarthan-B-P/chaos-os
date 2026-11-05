// Chapter 11: code tour: where each idea lives, so the team can open the right file live.
module.exports = (h) => [
  h.H1("11. Code tour: where each idea lives"),
  h.Lead("When a teacher says \"show me the code\", open the file below and explain the function in two " +
    "sentences. All paths are relative to the repository root."),

  h.H2("11.1 The experiment engine (controller/chaosctl)"),
  h.table(["Idea", "File → function", "What to say"], [
    ["Open-model load", "load.py → LoadGenerator.run", "Sends on a fixed schedule whatever the replies; records every request"],
    ["Recovery definition", "analysis.py → analyze, healthy_streak", "1 s windows, 99% / 300 ms, 5 healthy windows, sub-window recovery time"],
    ["One trial", "experiment.py → run_trial", "Reset, warm up, inject, detect, remediate, measure, reset"],
    ["Remediation loop", "experiment.py → remediate", "Observe → propose → validate (→ ask a human) → act → wait; shared with on-call"],
    ["Fault injection", "scenarios.py → SCENARIOS", "docker kill and Toxiproxy toxics; held-out flag"],
    ["Recovery actions", "actions.py → ACTIONS, run_action", "Each action is an Ansible playbook with a 45 s timeout"],
    ["Safety shield", "safety.py → SafetyValidator.check", "Five rules in order; needs_approval for human mode"],
    ["Results storage", "store.py → save, summary, trial", "SQLite with additive migrations"],
    ["One experiment at a time", "runner.py → lab_lock", "A file lock on the shared volume, across containers"],
    ["CLI", "__main__.py", "list, run, train, learning-curve, report, explain, gate, oncall, drill"],
  ], [1.6, 2.4, 3.6]),
  h.spacer(),

  h.H2("11.2 Learning and AI"),
  h.table(["Idea", "File → function", "What to say"], [
    ["Bandit features", "bandit.py → features", "8 numbers from symptoms; latencies log-scaled"],
    ["LinUCB", "bandit.py → LinUCB.scores, update", "Per-action ridge regression plus an uncertainty bonus"],
    ["Training + learning curve", "learning.py → train, learning_curve", "Training failures only (asserted); 30 replay orders"],
    ["Policies", "policies.py → RuleBased, Heuristic, Bandit, LLM, Guided*", "Same inputs for all; SRE_GUIDANCE text for the ablation"],
    ["OpenAI client", "llm.py → chat, chat_json, chat_tools", "gpt-4o-mini, temperature 0; the key never appears in errors"],
    ["LLM agent", "agent.py → AgentPolicy.choose, run_tool", "Look before acting (1-5 tool calls); trail recorded; Toxiproxy hidden"],
    ["Post-mortems, Q&A", "insights.py → explain_trial, explain_incident, ask", "Only measured data goes in; cached"],
  ], [1.6, 2.4, 3.6]),
  h.spacer(),

  h.H2("11.3 On-call mode"),
  h.table(["Idea", "File → function", "What to say"], [
    ["Webhook receiver", "oncall.py → _Webhook, serve", "Alertmanager POSTs here; repeated notifications are merged"],
    ["Rules of engagement", "oncall.py → handle", "Autopilot on? Lab free? Otherwise stand down"],
    ["Confirm before acting", "oncall.py → _respond", "4 s of probe traffic; healthy = stale page, no incident"],
    ["Working an incident", "oncall.py → _work_incident", "Same remediate loop; sustained recovery or escalation"],
    ["Human approval", "oncall.py → _ask_human; incidents.py → decide, expire", "First decision wins; 60 s then fail safe"],
    ["Records and scorecard", "incidents.py → scorecard", "Matches each fault to the agent's incident; detect / engage / recover"],
    ["SLI", "app/traffic/traffic.py", "good = 200 within 300 ms; counters for Prometheus"],
    ["SLO and alerts", "observability/prometheus/rules/slo.yml", "Recording rules, page and ticket alerts"],
    ["Alert tests", "observability/prometheus/tests/slo_test.yml", "Outage pages, blip does not, slowness counts, lost SLI tickets"],
    ["Operator console", "dashboard/server/app.py → oncall_status, decide_approval, break_lab, _chaos_loop", "SLO, approvals, Break it, monkey, rollback"],
    ["On-call page", "dashboard/web/src/pages/OnCall.jsx", "Approval card, KPIs, timeline, controls, scorecard, history"],
  ], [1.6, 2.6, 3.4]),
  h.spacer(),

  h.H2("11.4 DevOps"),
  h.table(["Idea", "File", "What to say"], [
    ["The lab", "docker-compose.yml (+ override, prod, tunnel overlays)", "11 services; health checks; isolated project names"],
    ["Pipeline", "Jenkinsfile; jenkins/jobs/chaos-os-ci/config.xml", "10 stages; multibranch; polls GitHub every 5 min"],
    ["Release gate", "resilience-gate.yml; __main__.py → cmd_gate", "6 faults with deadlines"],
    ["On-call drill", "__main__.py → cmd_drill", "Inject unannounced; pass only if healed in time"],
    ["Security scan", "scripts/security-scan.sh; .gitleaks.toml; .trivyignore.yaml", "Secrets, deps, Dockerfiles, images, SBOMs"],
    ["Deployment", "deploy/ansible/deploy.yml; deploy/caddy/Caddyfile", "Provision a VM; HTTPS + login in front"],
    ["Sharing", "deploy/share.ps1; deploy/docker-compose.tunnel.yml", "Cloudflare quick tunnel, no ports opened"],
    ["Measurement campaign", "scripts/oncall_campaign.py", "Unannounced faults through the dashboard API; scripted operator"],
    ["Paper figures", "docs/paper/make_figures.py, make_tables.py", "Every chart and table regenerated from the database"],
  ], [1.6, 2.8, 3.2]),
];
