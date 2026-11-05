// Chapter 1: the big picture, elevator pitches, project at a glance, glossary.
module.exports = (h, R, F) => {
  const camp = R.campaign || {};
  const faults = Object.values(camp).reduce((a, c) => a + c.n, 0);
  const healed = Object.values(camp).reduce((a, c) => a + c.healed, 0);
  return [
    h.H1("1. The big picture"),
    h.Lead("CHAOS OS is a resilience lab. It breaks a small online shop on purpose, lets different " +
      "\"responders\" try to fix it, measures exactly how long every fix takes, keeps every action " +
      "safe, learns which fix works best, and stops a bad release before it ships."),
    h.P("If you remember one sentence, remember this one: **CHAOS OS turns \"we think our system recovers " +
      "from failures\" into a measured, repeatable, automatically tested fact.**"),

    h.H2("1.1 The problem we solve"),
    h.P("Every real system fails: a cache server crashes, a database becomes slow, the network drops packets, " +
      "an application process dies. Teams usually write a _runbook_ (\"if X breaks, restart Y\") and hope it " +
      "works. Three things go wrong in practice:"),
    ...h.bullets([
      "**Nobody measures whether the runbook is right.** \"Restart it\" is the default answer, but our data " +
      "shows it is the wrong answer for most failures.",
      "**Automation can make things worse.** A script that restarts things in a loop, or touches the wrong " +
      "service, turns a small incident into a big one. Automation needs guardrails.",
      "**Releases are not tested against failures.** Unit tests check that code works when everything is " +
      "healthy. They do not check that the system still _recovers_ when something breaks.",
    ]),
    h.P("CHAOS OS attacks all three: it measures every fix against every failure, puts a safety validator " +
      "(and a human, for risky actions) between any decision and its execution, and runs real failures in " +
      "the CI/CD pipeline so a release that cannot recover is blocked."),

    h.H2("1.2 Elevator pitches (memorise one)"),
    ...h.callout("explain", "The 30-second version", [
      "\"We built a lab that injects real failures into a web shop under live traffic. Five kinds of responder " +
      "(a classic runbook, expert rules, a machine-learning bandit, an LLM, and an LLM agent with tools) try to " +
      "fix each failure; a safety validator checks every action first. We measure recovery for every single " +
      "request, learn which fix is best, run an always-on AI on-call engineer that heals failures nobody " +
      "announced, and make Jenkins refuse any release that cannot recover.\"",
    ]),
    ...h.callout("explain", "The 2-minute version (add these after the 30 seconds)", [
      "\"Our first finding is that **there is no universal fix**: each failure has a different best action, and " +
      "the classic 'restart it' runbook fails exactly where restarting is the wrong answer.",
      "Second, a **contextual bandit** (a light-weight learning algorithm) learned the right fix from logged " +
      "experiments, without anyone writing rules, and it **generalised to a failure it had never seen** " +
      "(a Redis network cut).",
      "Third, we tested **gpt-4o-mini** carefully with an ablation study: one paragraph of general SRE advice " +
      "changed its behaviour far more than tools did, for better on network faults and for worse on crashes; " +
      "tools alone only added seconds, but tools plus advice was the most robust combination.",
      "Fourth, the lab now runs like production: **SLOs, error budgets and burn-rate alerts** page an " +
      "**on-call agent** that confirms the problem, fixes it through the safety validator, asks a human before " +
      "anything risky, and writes the post-mortem.",
      "And it is all **DevOps end to end**: Docker Compose, Ansible, Jenkins with resilience, security and " +
      "on-call gates, Prometheus, Grafana, Alertmanager, and one-command HTTPS deployment.\"",
    ]),

    h.H2("1.3 The project at a glance"),
    h.table(["What", "Number"], [
      ["Containers in the running lab", "11 (shop, data, fault injection, observability, agent, dashboard)"],
      ["Failure scenarios", "7 (5 training + 2 held out, never used for training)"],
      ["Recovery actions", "6 (none, restart Redis / Postgres / API, cache bypass, warm cache)"],
      ["Responders (policies) compared", "5 main + 2 ablation variants + 1 red-team policy"],
      ["Experiment trials recorded", `${R.trial_count ?? "–"} (every request of every trial timed)`],
      ["LLM ablation trials (2 x 2 design)", `${R.ablation_trials ?? "–"}`],
      ["Unannounced faults in the on-call campaign", faults ? `${faults} (${healed} healed)` : "–"],
      ["Automated tests", `${F.tests?.unit ?? 45} unit tests + ${F.tests?.promtool ?? 4} alert-rule tests + 6 gate checks + 1 on-call drill`],
      ["Jenkins pipeline stages", "10 (build to teardown)"],
      ["Lines of code (non-blank)", `${F.loc_total ?? "about 6,100"} across ${F.files ?? 132} files`],
      ["Unsafe actions executed", "0"],
    ], [3, 4]),
    h.spacer(),

    h.H2("1.4 The five headline results"),
    ...h.numbered([
      "**No single fix works everywhere.** Each of the 5 training failures has a different best action. " +
      "Choosing the wrong one costs hundreds to over a thousand failed requests (Figure in Chapter 9).",
      "**The learned bandit matches expert rules without hand-written rules** and generalises to the unseen " +
      "Redis network partition (3/3 recovered, 0.8 s), where the classic runbook fails 0/3.",
      "**For the LLM, advice and evidence interact.** Generic SRE guidance replaced gpt-4o-mini's \"restart " +
      "first\" habit with a \"bypass first\" habit (Redis latency 50 s → 3 s, but a crashed database was never " +
      "restarted); tools alone only added seconds; tools plus guidance handled both kinds of fault.",
      "**The on-call agent heals failures nobody announced**, end to end: alert, confirmation, safe fix, human " +
      "approval when needed, post-mortem.",
      "**Safety held: zero unsafe actions** in every experiment, including deliberate red-team attacks, and the " +
      "CI gate blocks a one-character bug that unit and smoke tests miss.",
    ]),

    h.H2("1.5 How to use this guide"),
    ...h.bullets([
      "**Chapters 2-3** teach the background (DevOps, SRE, chaos engineering, AI) from zero. Read them first if a " +
      "term is new.",
      "**Chapters 4-8** explain every part of the system: what it does, why it exists, and where the code is.",
      "**Chapter 9** has every result, with the numbers you should quote.",
      "**Chapter 10** is for defending the project: limitations, the demo script, about 50 likely teacher " +
      "questions with answers, and a split of who explains what.",
      "**Chapter 11** is a code tour (which file and function to open for each idea) and **Chapter 12** " +
      "reprints the key configuration files with notes.",
      "Look for the coloured boxes: **orange = say this to the teacher**, **grey = remember this**, " +
      "**blue = likely question**, **yellow = common mistake**.",
    ]),

    h.H2("1.6 Glossary (the 40 words you must know)"),
    h.table(["Term", "Meaning in one line"], [
      ["Chaos engineering", "Breaking a system on purpose, in a controlled way, to learn how it fails and recovers."],
      ["Fault / failure scenario", "One specific way we break the shop (e.g. kill Redis, slow down Postgres)."],
      ["Fault injection", "The act of causing the fault. We use Docker (kill containers) and Toxiproxy (network)."],
      ["Toxiproxy", "A proxy between the API and Redis/Postgres that can add latency or cut the connection."],
      ["Recovery action", "One fix we can apply, implemented as an Ansible playbook."],
      ["Policy / responder", "The decision-maker that picks a recovery action from the symptoms."],
      ["Symptoms", "What an operator can observe: error rate, p95 latency, API up?, Redis/Postgres reachable + probe ms."],
      ["Trial", "One experiment: reset, warm up, inject, detect, remediate, measure."],
      ["Recovery time", "Seconds from fault injection until traffic is healthy again (strict definition in 4.3)."],
      ["p95 latency", "95% of requests were faster than this value."],
      ["Safety validator", "Code that checks every proposed action against safety-policy.yml before it runs."],
      ["Allowlist", "The explicit list of things that are permitted; anything else is refused."],
      ["Human-in-the-loop", "A person must approve high-impact actions (here: restart_postgres in on-call mode)."],
      ["Red team", "A deliberately hostile tester; our adversarial policy proposes unsafe actions on purpose."],
      ["Contextual bandit", "A learning algorithm that picks an action based on context and learns from rewards."],
      ["LinUCB", "The specific bandit algorithm we use: one linear model per action plus an uncertainty bonus."],
      ["Reward", "How good an action was: faster healing = higher; minus a safety cost for risky actions."],
      ["Held-out scenario", "A failure never used for designing or training, used only to test generalisation."],
      ["LLM", "Large language model; we use OpenAI gpt-4o-mini only."],
      ["LLM agent / tool calling", "An LLM that can call functions (query metrics, read logs) before deciding."],
      ["Ablation study", "Turning features on/off one at a time to see which one causes an effect."],
      ["SRE", "Site Reliability Engineering: running services with engineering discipline (Google's practice)."],
      ["SLI", "Service Level Indicator: what we measure (share of good user requests)."],
      ["SLO", "Service Level Objective: the target (99% of requests good)."],
      ["Error budget", "The allowed bad part: 1% of requests. Spending it too fast is an emergency."],
      ["Burn rate", "How fast the error budget is being spent; 1x = exactly on budget, 14.4x = paging speed."],
      ["Page / ticket", "Page = urgent alert that wakes someone (here the agent); ticket = look at it later."],
      ["Alertmanager", "Prometheus' alert router: groups, de-duplicates and sends alerts (here: webhook to the agent)."],
      ["Synthetic users", "A small service that sends steady fake customer traffic and measures the SLI."],
      ["On-call agent", "Our always-on program that responds to pages, like a human on-call engineer."],
      ["MTTD / MTTR", "Mean (we report median) time to detect / to recover."],
      ["Post-mortem", "A blameless write-up of an incident: what happened, what was done, what we learn."],
      ["Docker / container", "A packaged, isolated process with everything it needs to run."],
      ["Docker Compose", "A file that describes many containers and starts them together."],
      ["Ansible / playbook", "Automation tool; a playbook is a YAML list of steps (here: our recovery actions)."],
      ["CI/CD / Jenkins", "Automatic build-test-release pipeline; Jenkins is the server that runs it."],
      ["Resilience gate", "Pipeline stage that injects real faults and fails the build if recovery is too slow."],
      ["DevSecOps", "Security checks built into the pipeline (secrets, vulnerable dependencies, image CVEs, SBOM)."],
      ["SBOM", "Software Bill of Materials: the list of every package inside an image."],
      ["Reverse proxy (Caddy)", "The single public entry point that adds HTTPS and a login in front of the app."],
    ], [2, 5]),
  ];
};
