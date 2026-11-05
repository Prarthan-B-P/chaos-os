// Chapter 7: the DevOps machinery: Jenkins, gates, security, deployment, dashboard, gen AI.
const path = require("path");
const FIG = (f) => path.join(__dirname, "..", "..", "paper", "figures", f);

module.exports = (h, R, F) => {
  const sec = F.security || {};
  const ci = F.ci || {};
  return [
    h.H1("7. The DevOps machinery"),
    h.Lead("Everything in CHAOS OS is automated and written as code: the lab (Compose), the fixes (Ansible), " +
      "the rules (YAML policies), the alerts (Prometheus rules with unit tests), the pipeline (Jenkinsfile and " +
      "job XML), and the deployment (Ansible + Caddy)."),

    h.H2("7.1 The Jenkins pipeline, stage by stage"),
    ...h.figure(FIG("pipeline.png"), "The Jenkins pipeline. Orange stages are gates that only chaos or security " +
      "checks can fail; any failed stage stops the release.", 6.4),
    h.table(["Stage", "What happens", "Fails the build when"], [
      ["1. Build images", "docker compose --profile tools build (all images)", "Any image fails to build"],
      ["2. Unit tests", "45 Python tests inside the controller image", "Any test fails"],
      ["3. Alert rules", "promtool check config, promtool test rules (4 cases), amtool check-config", "A rule or route is wrong"],
      ["4. Security scan", "gitleaks (code + history), Trivy fs (deps + Dockerfiles), Trivy images, SBOMs", "A secret, a HIGH/CRITICAL misconfiguration or fixable dependency CVE, or a fixable CRITICAL image CVE"],
      ["5. Deploy lab", "docker compose up -d --wait in an isolated project, no host ports", "A service never becomes healthy"],
      ["6. Smoke test", "A throwaway container calls the shop through nginx", "The shop does not answer correctly"],
      ["7. Resilience gate", "6 real faults with a fixed fix and a deadline (resilience-gate.yml)", "Any recovery misses its deadline"],
      ["8. On-call drill", "Kill Redis without telling the agent; it has 120 s", "No incident, or not healed in time"],
      ["9. Reports", "Archive resilience report, security reports, SBOMs, drill output, logs", "-"],
      ["10. Teardown", "docker compose down -v (always, even on failure)", "-"],
    ], [1.5, 3.4, 2.6]),
    h.spacer(),
    h.P("**Isolation:** each build uses the project name `chaosos-ci-<executor number>` and only the main Compose " +
      "file (no host ports), so builds of different branches can run side by side and never touch the lab on your " +
      "laptop. Sources reach scanner containers through stdin (`tar`), never bind mounts, because Jenkins talks to " +
      "the host's Docker engine (\"Docker outside of Docker\")."),
    ...(ci.build ? [h.P(`**Measured:** build #${ci.build} of main finished **${ci.result}** in ${ci.duration}. ` +
      (ci.stages || []).map((s) => `${s.name} ${s.duration}`).join(", ") + ".")] : []),

    h.H2("7.2 The resilience gate and the demo bug"),
    h.P("`resilience-gate.yml` lists the failures every release must survive and the deadline for each " +
      "(roughly 2x the median measured locally, for headroom on a busier CI host):"),
    h.table(["Failure", "Fix used", "Deadline"], [
      ["redis_down", "restart_redis", "10 s"], ["redis_down", "cache_bypass", "10 s"],
      ["redis_latency", "cache_bypass", "10 s"], ["postgres_latency", "warm_cache", "15 s"],
      ["postgres_down", "restart_postgres", "15 s"], ["api_crash", "restart_api", "20 s"],
    ], [2.5, 2.5, 1.5]),
    h.spacer(),
    ...h.callout("explain", "The demo that convinces teachers", [
      "Branch `demo/broken-cache-bypass` has a one-character bug: the cache-bypass endpoint writes the wrong flag " +
      "key. It returns 200 OK, the Ansible playbook reports success, unit tests pass, the smoke test passes, but " +
      "nothing actually changes. Only the resilience gate catches it: both cache-bypass checks never recover, so " +
      "Jenkins shows that branch **red** while `main` stays **green**.",
    ]),

    h.H2("7.3 Alerts are code, and code is tested"),
    h.P("`observability/prometheus/tests/slo_test.yml` feeds synthetic time series into the real rules and checks " +
      "four behaviours: a real outage pages within seconds and stops paging after recovery; a 5-second blip " +
      "does not page; slow responses burn the budget like errors; losing the synthetic traffic raises a ticket " +
      "after 30 s. These run in CI with `promtool test rules`."),

    h.H2("7.4 DevSecOps: the security scan"),
    h.P("`scripts/security-scan.sh` runs four checks. Policy: any secret, any HIGH/CRITICAL misconfiguration " +
      "or fixable dependency vulnerability, or a fixable CRITICAL vulnerability in an image fails the build. " +
      "Accepted risks are listed in `.trivyignore.yaml`, each with a written justification."),
    h.table(["Check", "Tool", "First run found", "What we did"], [
      ["Secrets in code and history", "gitleaks 8.21", sec.gitleaks || "0 leaks in all commits", "Custom rule for current OpenAI key formats; .env and secrets never leave the machine"],
      ["Python dependencies", "Trivy 0.56 fs", "ansible-core 2.17.5: 2 HIGH CVEs (CVE-2024-8775, CVE-2026-11332)", "Upgraded to ansible-core 2.21.6 everywhere"],
      ["npm dependencies (incl. dev)", "Trivy fs", "vite 5.4.10: 1 HIGH, 12 MEDIUM, 3 LOW; esbuild 1 MEDIUM; no lockfile", "Vite 6.4.5 + plugin-react 4.7.0; package-lock.json + npm ci (reproducible)"],
      ["Dockerfiles (IaC)", "Trivy misconfig", "12 Dockerfiles without a non-root USER (HIGH); 1 CRITICAL that was a false positive", "Non-root for api, traffic, frontend (unprivileged nginx), Toxiproxy, Prometheus, Alertmanager, Grafana; 5 justified exceptions + 1 false positive documented"],
      ["Built images", "Trivy image", "frontend base (nginx 1.27, old Alpine): 3 CRITICAL + 58 HIGH; Docker CLI and gosu binaries: 1 CRITICAL each (old Go)", "nginx-unprivileged 1.30 + apk upgrade (0 left); Docker CLI 29.8; gosu CVE accepted until 2027-03-01 (unreachable code); CycloneDX SBOM per image (441 components)"],
    ], [1.6, 1.2, 2.4, 2.8]),
    h.spacer(),
    ...h.callout("remember", "Justified exceptions (accepted risks)", [
      "Controller, dashboard and the Ansible runner must use the host Docker socket to inject faults and restart " +
      "containers, which requires root inside the container. They have no public ports in production and every " +
      "action passes the safety validator. Postgres's official entrypoint drops root itself. One Trivy finding " +
      "was a false positive (`ANSIBLE_HOST_KEY_CHECKING` contains the word KEY).",
    ]),

    h.H2("7.5 Deployment"),
    ...h.bullets([
      "**Production overlay** (`deploy/docker-compose.prod.yml`): Caddy is the only public entry point, with " +
      "automatic HTTPS (Let's Encrypt via a free sslip.io name), a bcrypt login, security headers, Grafana " +
      "under /grafana, and restart policies on every service.",
      "**One-command provisioning** (`deploy/ansible/deploy.yml`, run by `deploy.ps1` from a container so it " +
      "works on Windows): firewall rules (including Oracle Cloud's iptables quirk), Docker install, swap on " +
      "small servers, git clone, secrets in an owner-only .env, seeding the experiment history, `compose up " +
      "--wait`, and an HTTPS + login check from outside.",
      "**No server, no card:** `deploy/share.ps1` runs the same production overlay on the laptop with a " +
      "Cloudflare quick tunnel; nothing is opened on the router, and the same login protects it.",
    ]),

    h.H2("7.6 The evidence dashboard, page by page"),
    ...h.figure(FIG("screens/dashboard-overview.png"), "The evidence dashboard's Overview: headline numbers, Ask the " +
      "lab (answers come from measured data only) and the leaderboard of responders per failure.", 6.0),
    h.table(["Page", "What it shows / does"], [
      ["Overview", "Headline numbers, Ask the lab (gpt-4o-mini answers only from measured data), AI analysis of results, charts"],
      ["On-call", "SLO, burn rate, 24 h error budget, live incident timeline, approvals, Break it, chaos monkey, scorecard, incident history with post-mortems"],
      ["Matrix", "Every failure x every fixed action: recovery time and failed requests"],
      ["Policies", "Ranked responders per failure, training and held out"],
      ["Learning", "The bandit's learning curve against the fixed rules"],
      ["Incidents", "Every experiment as a timeline: symptoms, actions, verdicts, the LLM's reason, the agent's tool trail, post-mortem"],
      ["Run", "Launch an experiment (failure + responder or fixed action) and watch the live log"],
      ["Safety", "The safety rules, blocked proposals, and a one-click red-team test"],
    ], [1.3, 5.5]),
    h.spacer(),

    h.H2("7.7 Generative AI features (gpt-4o-mini only)"),
    ...h.bullets([
      "**Decide:** the `llm` policies pick actions; the `llm_agent` policies investigate with tools first.",
      "**Explain:** post-mortems for experiments and on-call incidents, and a results analysis.",
      "**Ask the lab:** free questions answered from the measured data only (the model is told never to invent " +
      "numbers, and to say when the data cannot answer).",
      "**Cost and privacy:** temperature 0, small prompts; the whole project's AI usage costs cents. The key is " +
      "only in `.env` (git-ignored), never in code, logs or chat. CI runs without a key.",
    ]),
  ];
};
