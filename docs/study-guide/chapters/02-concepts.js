// Chapter 2: background concepts, explained from zero.
module.exports = (h) => [
  h.H1("2. Background concepts, from zero"),
  h.Lead("This chapter explains every idea the project is built on. Each section ends with how that idea " +
    "appears in CHAOS OS, so you can connect theory to our code."),

  h.H2("2.1 DevOps and CI/CD"),
  h.P("**DevOps** is the practice of developers and operations working as one team, automating the path from " +
    "code to production and learning from how the system behaves in production. Its core loop is: plan, " +
    "code, build, test, release, deploy, operate, monitor, and feed what you learn back into planning."),
  h.P("**CI (Continuous Integration)** means every change is built and tested automatically. **CD (Continuous " +
    "Delivery/Deployment)** means a change that passes every check is ready to ship (or ships automatically). " +
    "The pipeline is a series of _gates_; if any gate fails, the change stops."),
  ...h.callout("remember", "In CHAOS OS", [
    "Jenkins runs our pipeline on every branch. Besides normal gates (build, unit tests, smoke test), it has " +
    "three unusual ones: a **security scan**, a **resilience gate** that injects real failures, and an **on-call " +
    "drill** that checks the AI agent can heal an unannounced failure.",
  ]),

  h.H2("2.2 Containers, Docker and Docker Compose"),
  h.P("A **container** packages a program with everything it needs (libraries, config) so it runs the same on " +
    "any machine. **Docker** builds images and runs containers. **Docker Compose** describes a whole " +
    "multi-container application in one YAML file (`docker-compose.yml`): which images, which network, which " +
    "volumes, which health checks, which order to start in."),
  h.P("Two Compose ideas matter for us: **health checks** (`docker compose up --wait` waits until every " +
    "service is healthy) and **project names** (every lab gets a name such as `chaosos` or `chaosos-ci-2`, so " +
    "several labs can run side by side on one machine without touching each other)."),
  ...h.callout("remember", "In CHAOS OS", [
    "The lab is 11 containers in one Compose project. We also use overlay files: `docker-compose.override.yml` " +
    "adds local ports, `deploy/docker-compose.prod.yml` adds the HTTPS proxy for servers, and " +
    "`deploy/docker-compose.tunnel.yml` shares the lab through a Cloudflare tunnel.",
  ]),

  h.H2("2.3 Chaos engineering"),
  h.P("Chaos engineering was popularised by Netflix (Chaos Monkey randomly terminated servers in production). " +
    "The principle: _you do not know how your system fails until you make it fail_. A chaos experiment has a " +
    "**steady-state hypothesis** (\"traffic is healthy\"), a **fault** (\"kill the cache\"), a controlled " +
    "**blast radius**, and a **measurement** of what happened."),
  h.P("Most chaos tools (Chaos Mesh, LitmusChaos, Gremlin) only _inject_ faults. CHAOS OS goes further: it " +
    "compares many _recovery strategies_ for each fault, learns which one is best, and turns the results " +
    "into a release gate."),

  h.H2("2.4 SRE: SLIs, SLOs, error budgets and burn rates"),
  h.P("**Site Reliability Engineering (SRE)** is Google's way of running services. Its key tools:"),
  ...h.bullets([
    "**SLI (indicator):** a measurement of user experience. Ours: the share of user requests that return " +
    "200 OK within 300 ms.",
    "**SLO (objective):** the target for the SLI. Ours: 99% of requests good.",
    "**Error budget:** what the SLO allows to be bad: 1% of requests. At our steady 2 requests/s that is " +
    "172,800 requests/day, so 1,728 bad requests per day are \"allowed\".",
    "**Burn rate:** how fast the budget is being spent. If 1% of requests are bad, the burn rate is 1x (exactly " +
    "on budget). If 14.4% are bad, it is 14.4x: at that speed a 30-day budget would be gone in 2 days.",
  ]),
  h.P("**Why 14.4x?** It comes from the Google SRE Workbook: burning 2% of a 30-day budget in one hour " +
    "equals a burn rate of 14.4 (0.02 x 720 hours). It is the standard threshold for an urgent page."),
  h.P("**Multi-window alerting.** A page fires only if the burn rate is high over a **long** window (it is a " +
    "real problem, not a blip) **and** a **short** window (it is still happening). Our lab compresses time: " +
    "1 minute and 20 seconds instead of 1 hour and 5 minutes. A 5-second blip does not page; a real outage " +
    "pages in about 10-15 seconds; the page stops soon after recovery."),
  ...h.callout("explain", "Worked example to say out loud", [
    "\"At 2 requests per second, a 1-minute window holds 120 requests. If Redis dies, every request fails. " +
    "After about 9 seconds, 18 of the last 120 requests are bad: 15%, which is a burn rate above 14.4. The " +
    "20-second window is already at 45%. Both windows are over the line, so Prometheus fires the page.\"",
  ]),

  h.H2("2.5 Observability: metrics, dashboards, alerts"),
  h.P("**Prometheus** collects numeric metrics by _scraping_ an HTTP `/metrics` endpoint every few seconds " +
    "(ours: every 5 s) and stores them as time series. **Recording rules** pre-compute useful series (our bad " +
    "ratios over 20 s, 1 min, 10 min, 1 h). **Alerting rules** turn conditions into alerts."),
  h.P("**Alertmanager** receives alerts, groups and de-duplicates them, silences or inhibits them, and routes " +
    "them to a receiver (email, chat, or in our case a **webhook** that wakes the on-call agent). **Grafana** " +
    "draws dashboards from Prometheus and shows **annotations** (our experiments and the agent mark fault " +
    "injection and fixes on the graphs)."),

  h.H2("2.6 Infrastructure as code with Ansible"),
  h.P("**Ansible** automates operations with YAML **playbooks**: a list of tasks, each using a module " +
    "(run a command, call a URL, assert a condition). It is _idempotent_ and readable, which makes it auditable. " +
    "Every recovery action in CHAOS OS is an Ansible playbook, and the playbooks enforce their own " +
    "**service allowlist** (a second layer of safety under the validator). Ansible is also used to " +
    "**provision a cloud server** in one command (`deploy/ansible/deploy.yml`)."),

  h.H2("2.7 Jenkins"),
  h.P("**Jenkins** is an open-source automation server. A `Jenkinsfile` (pipeline as code) lists the stages. " +
    "Our job is a **multibranch** pipeline defined as code (`jenkins/jobs/chaos-os-ci/config.xml`): Jenkins " +
    "polls GitHub every 5 minutes and builds every branch. Jenkins runs in its own container and controls the " +
    "host's Docker engine through the Docker socket (\"Docker outside of Docker\"), so each build starts its own " +
    "isolated lab (`chaosos-ci-<executor>`) without any host ports."),

  h.H2("2.8 Contextual bandits and LinUCB"),
  h.P("A **multi-armed bandit** is a learning problem: you repeatedly choose one of several actions (\"arms\") and " +
    "get a reward. A **contextual** bandit also sees a context (for us: the symptoms) and learns which action " +
    "is best _for that context_. It is simpler than full reinforcement learning because each decision is " +
    "judged on its own immediate reward."),
  h.P("**LinUCB** keeps, for every action, a small linear model that predicts reward from the context " +
    "features, plus an **upper confidence bound** bonus that is large when the model is unsure. Choosing the " +
    "highest \"prediction + bonus\" balances exploring unknown actions and exploiting good ones. At decision " +
    "time in the lab we use the prediction only (greedy), because exploration happens in the logged experiments."),
  ...h.callout("remember", "Why a bandit and not deep learning?", [
    "We have a few hundred logged decisions, not millions. A linear bandit with 8 features learns from small " +
    "data, trains in milliseconds, is explainable (you can read its weights), and runs without a GPU.",
  ]),

  h.H2("2.9 LLMs, tool calling and agents"),
  h.P("A **large language model (LLM)** predicts text. We use **OpenAI gpt-4o-mini** only (cheap and fast). " +
    "With **JSON mode** it answers in a fixed structure (`{\"action\": ..., \"reason\": ...}`). With **tool " +
    "calling**, the model can ask the program to run a function (e.g. \"query Prometheus\", \"read the Redis " +
    "logs\"), read the result, and continue: this loop of reasoning and acting is called an **agent** " +
    "(the ReAct pattern). An agent can investigate before acting, but every extra call costs time."),
  ...h.callout("warn", "Common mistake", [
    "Do not say \"the AI fixes the system\". Say: \"the LLM _proposes_ an action; the safety validator decides " +
    "whether it may run; Ansible runs it; and we measure whether it worked.\"",
  ]),

  h.H2("2.10 Safety: guardrails, shields and human-in-the-loop"),
  h.P("Letting software act on production is dangerous. In safe reinforcement learning, a **shield** sits " +
    "between the learner and the world and blocks unsafe actions. Our **safety validator** is such a shield: " +
    "every proposal from every policy is checked against `safety-policy.yml` (approved environment, allowlist, " +
    "no repeats, action budget, approval for high-impact actions). In on-call mode, high-impact actions wait " +
    "for a **human** in the dashboard; if nobody answers in 60 s, the action is **not** run (fail safe)."),

  h.H2("2.11 DevSecOps and software supply chain"),
  ...h.bullets([
    "**Secret scanning** (gitleaks): finds passwords and API keys committed to code or hidden in git history.",
    "**Dependency scanning** (Trivy fs): matches pinned Python/npm packages against vulnerability databases (CVEs).",
    "**Misconfiguration scanning** (Trivy, IaC): flags risky Dockerfiles, e.g. containers running as root.",
    "**Image scanning** (Trivy image): finds vulnerable OS packages and libraries inside built images.",
    "**SBOM** (CycloneDX): a machine-readable list of everything inside each image, archived per build.",
  ]),

  h.H2("2.12 Reverse proxies, HTTPS and tunnels"),
  h.P("A **reverse proxy** is the single front door of a deployment. Ours, **Caddy**, gets free HTTPS " +
    "certificates automatically, asks for a login (bcrypt-hashed password), adds security headers, and " +
    "forwards to the dashboard and Grafana. Nothing else is reachable from the internet. Without a server, a " +
    "**Cloudflare quick tunnel** gives the laptop a temporary public HTTPS address by connecting outwards, so no " +
    "router port is opened."),
];
