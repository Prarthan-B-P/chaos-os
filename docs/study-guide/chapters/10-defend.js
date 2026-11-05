// Chapter 10: limitations, future work, demo script, viva questions, team split.
module.exports = (h) => {
  const qa = (q, a) => [...h.callout("question", q, a)];
  return [
    h.H1("10. Defending the project"),
    h.Lead("Teachers reward teams that know the weak spots of their own work. Say the limitations before you are " +
      "asked, and connect each one to a concrete next step."),

    h.H2("10.1 Limitations (say these yourself)"),
    ...h.bullets([
      "**One machine, one lab.** Docker Desktop on a laptop; absolute times depend on hardware and include " +
      "probing and Ansible overhead. The comparisons between responders are fair because they share conditions.",
      "**Small samples.** 2-3 trials per (failure, responder) pair. We show ranges, not confidence intervals.",
      "**Simple workload.** One read endpoint with random items; real traffic has hot keys, writes and bursts.",
      "**Seven fault types.** No disk, CPU, memory or multi-service cascading faults yet.",
      "**One-step decisions.** Policies pick one action at a time; the compound failure needs a coordinated " +
      "two-step plan, and nothing solved it.",
      "**The heuristic was written after seeing the data**, which is why it is strong.",
      "**LLM results vary** run to run even at temperature 0, and depend on one vendor model (gpt-4o-mini).",
      "**On-call detection is about 10-20 s** because the SLI uses 2 requests/s and 5 s scrapes; production " +
      "traffic would give faster, finer signals.",
      "**Some containers run as root** because they control Docker; this is documented and isolated, not ideal.",
    ]),

    h.H2("10.2 Future work"),
    ...h.bullets([
      "Sequence-aware policies (planning or reinforcement learning behind the same safety shield) for compound failures.",
      "A Kubernetes port with Chaos Mesh as the fault injector and canary releases gated on the SLO.",
      "More trials with confidence intervals and significance tests.",
      "Safe online exploration for the bandit in CI.",
      "Distributed tracing (OpenTelemetry) as an extra tool for the LLM agent.",
      "Error-budget policy: freeze releases automatically when the budget is spent.",
    ]),

    h.H2("10.3 The live demo (about 7 minutes)"),
    h.P("**10 minutes before:** start Docker Desktop, run `docker compose up -d --wait` and " +
      "`docker compose -f jenkins/docker-compose.yml up -d`, open tabs for the dashboard (:8090), Grafana " +
      "(:3000), Jenkins (:8081) and GitHub, and do one warm-up Break-it so the first live run is not a cold start. " +
      "Check that the top bar says healthy."),
    h.table(["Time", "Do", "Say"], [
      ["0:00", "Dashboard → Overview", "\"Everything you see is measured: trials, recovery, blocked unsafe actions.\""],
      ["0:40", "On-call → Failure: Surprise me → Break it", "\"I just broke the shop. The agent was not told what or when.\""],
      ["1:00", "Watch the incident timeline appear", "\"Users noticed, the SLO burned 14x too fast, Alertmanager paged the agent, it confirmed with its own traffic, chose a fix, the validator allowed it.\""],
      ["2:00", "Open the incident → post-mortem", "\"gpt-4o-mini wrote this from the incident record only.\""],
      ["2:45", "Break it: postgres_down → approval card → Approve", "\"Restarting the database is high impact, so the agent asks me. No answer in 60 s means it does nothing.\""],
      ["3:45", "Incidents → an LLM agent trial → tool trail", "\"The agent investigated with real tools before deciding; every call is auditable.\""],
      ["4:30", "Grafana → SLO and on-call row", "\"Here is the burn rate crossing the 14.4 line, and our annotations.\""],
      ["5:15", "Jenkins → main (green) vs demo/broken-cache-bypass (red)", "\"A one-character bug passed unit and smoke tests. The resilience gate blocked it. Every build also scans for secrets and CVEs and runs an unannounced on-call drill.\""],
      ["6:15", "Overview → Ask the lab (Ctrl+K)", "Let a teacher ask something; the answer comes from our data."],
    ], [0.7, 2.6, 4.2]),
    h.spacer(),
    ...h.callout("warn", "If something goes wrong", [
      "No internet: skip the AI parts; everything else is local. A run looks stuck: Overview → Reset lab. " +
      "\"Lab is busy\": an experiment or incident is running; wait. Jenkins down: show screenshots from this guide.",
    ]),

    h.H2("10.4 Viva questions with model answers"),
    h.H3("The project in general"),
    ...qa("What is CHAOS OS in one sentence?", "A lab that injects real failures into a web service, lets " +
      "different responders fix them behind a safety validator, measures every recovery, learns the best fix, " +
      "heals unannounced failures with an on-call agent, and gates releases on the results."),
    ...qa("Why is this a DevOps project and not just an AI project?", "The AI is one responder. The project is a " +
      "complete DevOps loop: infrastructure as code (Compose, Ansible), CI/CD with Jenkins and four kinds of " +
      "gates, monitoring and alerting (Prometheus, Grafana, Alertmanager), SLOs and incident response, " +
      "DevSecOps scanning, and automated HTTPS deployment."),
    ...qa("Why build your own lab instead of using Chaos Mesh, LitmusChaos or Gremlin?", "Those tools inject " +
      "faults. We needed to compare recovery strategies, learn from them and gate releases on the result. A " +
      "Kubernetes port with Chaos Mesh as the injector is future work; our policies, safety layer and gates " +
      "would stay the same."),
    ...qa("Why Docker Compose and not Kubernetes?", "It runs on a student laptop, starts in seconds and keeps " +
      "every fault easy to understand. The ideas (SLOs, safety shield, gates) do not depend on the orchestrator."),
    h.H3("Measurement"),
    ...qa("How exactly do you define \"recovered\"?", "Five consecutive 1-second windows in which at least 99% of " +
      "requests succeed and p95 latency is at most 300 ms, measured per request by our own load generator. " +
      "Recovery time is the send time of the first request after the last bad one."),
    ...qa("Why not measure recovery with Prometheus?", "It scrapes every 5 s, too coarse for 1-2 s recoveries. " +
      "The load generator times every request. Prometheus is used where minute-scale signals are right: SLO alerts."),
    ...qa("Why is the load generator \"open model\"?", "It sends a request every 50 ms regardless of replies. A " +
      "closed model would slow down during an outage and hide the damage."),
    ...qa("Are 2-3 trials enough?", "Enough to see clear differences such as 0/2 vs 2/2 and 50 s vs 3 s, not for " +
      "confidence intervals. We report ranges and list this as a limitation."),
    ...qa("Why are some trials marked invalid?", "If the 10 s before injection were not healthy, the trial did not " +
      "start from steady state, so its result would be meaningless; it is excluded automatically."),
    h.H3("Failures and fixes"),
    ...qa("Why does restarting Redis not fix redis_latency?", "Redis is healthy; the network to it is slow (800 ms, " +
      "above the API's 500 ms timeout). Restarting a healthy process changes nothing. Cache bypass removes Redis " +
      "from the request path."),
    ...qa("Why does cache bypass make a slow database worse?", "Every read then goes to the slow database, so the " +
      "connection pool fills up. Warming the cache in one bulk query keeps reads off the database instead."),
    ...qa("What is the compound failure and why is it unsolved?", "Redis killed while Postgres is slow. Cache bypass " +
      "is a trap (all load on the slow DB); the fix is restart Redis then warm the cache. Our policies choose one " +
      "action at a time from single-fault experience and never found that sequence."),
    ...qa("Why is restart_postgres high impact?", "It drops every database connection and in-flight query. It is " +
      "the most disruptive allowed action, so it costs the most in the reward and needs approval in on-call mode."),
    h.H3("Policies and machine learning"),
    ...qa("What is a contextual bandit and why not deep reinforcement learning?", "It learns which action is best for " +
      "a given context from rewards. Our decisions are judged by their immediate effect, data is small (hundreds " +
      "of steps), and we want explainability. A linear bandit trains in milliseconds and its weights can be read."),
    ...qa("What does the bandit see and how is it rewarded?", "8 features: bias, API down, Redis unreachable, " +
      "Postgres unreachable, log-scaled Redis and Postgres probe latency, error rate, p95. Reward = " +
      "max(0, 1 - time_to_heal/20 s) minus the action's safety cost."),
    ...qa("Isn't it memorising the failure names?", "It never sees them. The held-out Redis partition proves it: " +
      "never trained on, the bandit still chose cache bypass (3/3, 0.8 s) while the runbook failed 0/3."),
    ...qa("How do you stop test data leaking into training?", "Training reads only steps from training failures, and " +
      "the code asserts that no held-out scenario is present. Held-out failures were run only after policies were frozen."),
    ...qa("Why is the heuristic as good as the bandit?", "A person wrote it after studying the training results, so " +
      "it encodes the answers. The bandit reaches the same level without anyone writing rules, which scales to " +
      "many more failures than a person can study."),
    ...qa("Why did the learning-curve number change from 98%?", "98% was a snapshot on the 52 fixed-action steps. The " +
      "curve now replays every logged step, including the policies' and LLMs' mistakes, and the best action per " +
      "failure is re-measured from all of them. The conclusion (bandit far above the runbook, close to the expert " +
      "rules) is unchanged."),
    h.H3("LLM and agent"),
    ...qa("Why gpt-4o-mini?", "It is cheap and fast enough to sit inside an incident loop, and using one model keeps " +
      "comparisons fair. The whole project's AI usage cost a few cents."),
    ...qa("How do you stop the LLM from doing something dangerous?", "It only proposes. Every proposal passes the " +
      "safety validator (environment, allowlist, no repeats, budget, approval), and Ansible enforces its own " +
      "allowlist. In our runs the validator blocked the agent from repeating restart_postgres."),
    ...qa("What can the LLM agent do, and can it cheat?", "Read-only tools: PromQL queries, recent container logs, " +
      "container states, the readiness check. Toxiproxy (the fault injector) is invisible to every tool, so it " +
      "must diagnose from symptoms like a human."),
    ...qa("What did the ablation show?", "Advice changed the habit, not the reasoning: with the SRE paragraph the " +
      "model chose cache bypass first in all 14 trials, so Redis latency fell from 50 s to 3.3 s but the crashed " +
      "database was never restarted. Tools alone added 8-12 s without changing choices. Tools plus advice handled " +
      "both kinds of fault (10/14, the best LLM result). No LLM found warm_cache for the slow database; the bandit " +
      "did, from measured data."),
    ...qa("Isn't the guidance just giving it the answers?", "No failure or action names are in it: only general " +
      "SRE principles found in any SRE book (restarts don't fix slow networks; check down vs. slow). The same " +
      "paragraph was given with and without tools, so the comparison is fair."),
    ...qa("Are LLM results reproducible?", "Not perfectly, even at temperature 0, which is why we ran each pair twice " +
      "and report ranges, and keep every reason and tool call in the database for audit."),
    ...qa("Where is the OpenAI key? Could it leak?", "Only in the git-ignored .env. It is never printed or logged; " +
      "errors strip the request; gitleaks scans every commit and the history in CI; CI itself runs without a key."),
    h.H3("On-call mode"),
    ...qa("What is the difference between an experiment and on-call mode?", "In an experiment the controller knows " +
      "the fault and the start time. In on-call mode the agent is woken only by an SLO alert and must work out " +
      "what is wrong from symptoms."),
    ...qa("Explain SLO, error budget and burn rate.", "SLO: 99% of user requests good. Error budget: the 1% that may " +
      "be bad. Burn rate: how fast it is being spent; 14.4x is the standard paging threshold from the SRE Workbook " +
      "(2% of a 30-day budget in one hour)."),
    ...qa("Why two alert windows?", "The long window (1 min) proves it is a real problem, not a blip; the short " +
      "window (20 s) proves it is still happening, so the page stops soon after recovery. Our rule tests prove " +
      "both behaviours."),
    ...qa("Why does detection take 10-20 seconds?", "Five-second scrapes, rate windows and 2 requests/s of synthetic " +
      "traffic. Faster would mean more false pages; it is the classic speed vs. precision trade-off."),
    ...qa("Why does the agent re-check after a page?", "Alerts lag behind reality. The page is a trigger; live " +
      "traffic is the truth. This prevents \"fixing\" a system that is already healthy."),
    ...qa("What if nobody approves a high-impact action?", "After 60 s it expires and is not run (fail safe). The " +
      "agent tries other safe options or escalates to a human."),
    ...qa("What if the agent cannot fix it?", "It escalates and stops acting (no loops). The incident closes " +
      "automatically when the service is healthy again, and faults are rolled back after 5 minutes."),
    ...qa("How do you know the agent did not cheat?", "It runs in its own container and never reads the chaos log; " +
      "its only inputs are alerts, metrics, logs and its own probe traffic. The scorecard compares its incidents " +
      "with the chaos log afterwards."),
    ...qa("What stops an experiment and the agent from fighting over the lab?", "A shared lab lock on the results " +
      "volume. Only one actor (an experiment or an incident) owns the lab at a time; the agent stands down while " +
      "an experiment runs."),
    h.H3("DevOps, CI and security"),
    ...qa("Walk me through the pipeline.", "Build, unit tests, alert-rule tests, security scan, deploy an isolated " +
      "lab, smoke test, resilience gate, on-call drill, archive reports, teardown. Any failure stops the release."),
    ...qa("What does the resilience gate catch that tests miss?", "Behaviour under failure. The demo branch's " +
      "one-character bug returns 200 OK and passes unit and smoke tests, but cache bypass silently does nothing; " +
      "the gate's recovery deadlines fail the build."),
    ...qa("How do builds avoid interfering with each other?", "Each build runs its own Compose project " +
      "(chaosos-ci-<executor>) without host ports and tears it down with -v at the end."),
    ...qa("What did the security scan find?", "No secrets. Two HIGH CVEs in ansible-core (upgraded), one HIGH and " +
      "twelve MEDIUM advisories in the Vite build tool (upgraded), no lockfile (added, npm ci), twelve Dockerfiles " +
      "running as root (seven fixed, five justified, one false positive), and fixable CRITICAL CVEs in three images: " +
      "an old Alpine base under nginx (61 findings, now 0), an old Docker CLI (upgraded), and gosu in the official " +
      "Postgres image (accepted until March 2027 because it handles no untrusted input). Remaining HIGH findings are " +
      "reported, not hidden."),
    ...qa("Why do some containers still run as root?", "They control the host's Docker engine to inject faults and " +
      "restart containers, which needs root in the container. They have no public ports and every action is " +
      "validated; the exceptions are written down with reasons."),
    ...qa("What is an SBOM and why archive it?", "A list of every package in an image. When a new vulnerability is " +
      "announced, you can tell instantly which builds contain the affected package."),
    ...qa("How is it deployed and secured?", "Caddy is the only public entry point: automatic HTTPS, a bcrypt login, " +
      "security headers; everything else is private on Docker's network. Ansible provisions a server in one " +
      "command; without a server, a Cloudflare tunnel shares the laptop behind the same login."),
    ...qa("How do you know the alert rules are right?", "promtool unit tests replay synthetic series through the " +
      "real rules: an outage pages, a blip does not, slowness counts as bad, and losing traffic raises a ticket."),
    h.H3("Wrap-up"),
    ...qa("What are the main limitations?", "One laptop, small samples, a simple workload, seven fault types, " +
      "one-step decisions (the compound failure is unsolved), and LLM variability."),
    ...qa("What would you do next?", "Sequence-aware policies behind the same safety shield, a Kubernetes port with " +
      "Chaos Mesh and SLO-gated canaries, more trials with confidence intervals, and safe online learning in CI."),

    h.H2("10.5 Who explains what (suggested split for four people)"),
    h.table(["Member", "Owns", "Chapters"], [
      ["Member 1", "The problem, architecture, how experiments and recovery measurement work, the failures", "1, 3, 4"],
      ["Member 2", "Responders: runbook, heuristic, bandit, LLM, agent; learning curve; the ablation", "5, 9.1-9.4"],
      ["Member 3", "On-call mode: SLOs, burn-rate alerts, the agent, approvals, safety validator, scorecard", "2.4-2.5, 4.6, 6, 9.5"],
      ["Member 4", "DevOps: Jenkins, resilience gate, security scan, deployment, dashboard; runs the live demo", "7, 8, 10.3"],
    ], [1.2, 4.4, 1.6]),
    h.spacer(),
    ...h.callout("explain", "Final tip", [
      "When you are unsure, go back to the evidence: \"we measured it; here is the number; here is the trial in the " +
      "dashboard\". That is the whole spirit of the project.",
    ]),
  ];
};
