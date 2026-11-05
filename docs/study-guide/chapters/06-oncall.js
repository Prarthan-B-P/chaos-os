// Chapter 6: on-call mode, end to end.
const path = require("path");
const FIG = (f) => path.join(__dirname, "..", "..", "paper", "figures", f);

module.exports = (h, R) => {
  const t = R.timeline_incident?.match || {};
  return [
    h.H1("6. On-call mode: healing failures nobody announced"),
    h.Lead("In experiments the controller knows what it broke. In real life nobody tells you. On-call mode " +
      "makes the lab behave like production: steady user traffic, an SLO, burn-rate alerts, and an always-on " +
      "agent that is woken by a page, the way a human on-call engineer is."),
    ...h.figure(FIG("loop.png"), "The on-call control loop mapped onto MAPE-K (Monitor, Analyze, Plan, Execute " +
      "over shared Knowledge), the reference model for self-managing (autonomic) systems.", 5.6),

    h.H2("6.1 The story of one incident, step by step"),
    ...h.numbered([
      "**Fault.** Someone (the dashboard's Break-it button, the chaos monkey, or the CI drill) kills Redis. " +
      "The agent is not told; the chaos log is written to a table the agent never reads.",
      "**Users notice.** The synthetic users (2 requests/s) start counting errors.",
      "**Prometheus notices.** Every 5 s it recomputes the bad-request ratio over 20 s and 1 min. When both " +
      "exceed 14.4%, the alert `ShopSLOFastBurn` fires with severity page.",
      "**Alertmanager pages the agent** through a webhook (`POST http://oncall:8095/alerts`).",
      "**The agent checks the rules of engagement:** autopilot on? Is an experiment using the lab right now " +
      "(the shared lab lock)? If so, it stands down.",
      "**It confirms.** It sends its own probe traffic (10 req/s) for 4 s. If the probe is healthy, the page is " +
      "stale (the problem already went away) and no incident is opened.",
      "**It opens an incident** and runs the same remediation loop as experiments with the chosen responder " +
      "(heuristic by default; bandit, LLM or LLM agent selectable in the dashboard).",
      "**High-impact actions wait for you.** The dashboard shows an approval card (and the top bar turns orange " +
      "on every page). Approve, deny, or let it expire: after 60 s it is not run (fail safe).",
      "**It closes the incident only on sustained recovery** (5 healthy seconds), otherwise it **escalates** to a " +
      "human and does not keep retrying (no loops). An escalated incident is closed automatically once the " +
      "service is healthy again.",
      "**It writes the post-mortem** with gpt-4o-mini from the incident record, and marks everything on Grafana.",
    ]),
    ...h.figure(FIG("fig_oncall_timeline.png"), `A real unannounced redis_down (incident #1): the 20 s burn rate ` +
      `jumps first; the page fires when the slower 1 min window also crosses 14.4 (+${t.detect_s ?? "–"} s); the ` +
      `agent confirms, runs cache_bypass and traffic is healthy at +${t.recover_s ?? "–"} s.`, 6.4),

    h.H2("6.2 Why the agent re-checks every page"),
    h.P("Alerts are based on windows of the past, so they lag: a page can still be firing for a few seconds " +
      "after the problem is gone, and Alertmanager repeats a firing page every minute. Treating the page as a " +
      "_trigger_ and live traffic as the _truth_ prevents the agent from \"fixing\" a healthy system. This is the " +
      "same discipline human SREs follow: confirm before you act."),

    h.H2("6.3 Human-in-the-loop approvals"),
    ...h.bullets([
      "The safety policy says high-impact actions need approval in on-call mode (`approval.on_call: human`).",
      "The agent writes an approval request to the shared database; the dashboard shows it with the action, " +
      "its description, the responder's reason and the live symptoms.",
      "Only the **first** decision counts (approve or deny); a second click is refused. After 60 s the request " +
      "**expires** and the action is not run.",
      "Behind the HTTPS proxy, the approval is signed with the logged-in user's name (set by Caddy, not the " +
      "browser).",
    ]),
    ...h.figure(FIG("screens/oncall-approval-crop.png"), "The On-call page during an unannounced postgres_down: the " +
      "agent wants to restart Postgres (high impact) and waits for a human decision; the SLO is breaching and the " +
      "burn rate is far above the 14.4x paging line.", 6.2),

    h.H2("6.4 The chaos side: Break it, chaos monkey, rollback"),
    ...h.bullets([
      "**Break it:** inject a chosen or random failure from the dashboard, unannounced.",
      "**Chaos monkey:** when switched on, injects a random failure every ~10 minutes (randomised between 0.5x and " +
      "1.5x so it is not predictable), only when the lab is idle.",
      "**Rollback:** every injected fault is rolled back after 5 minutes at the latest, so an unattended lab " +
      "never stays broken.",
      "**One fault at a time:** a new injection first rolls the previous one back.",
    ]),

    h.H2("6.5 The scorecard: how we prove it works"),
    h.P("Every fault in the chaos log is matched to the first incident the agent opened within 10 minutes after " +
      "it. Three times are measured from the moment of injection:"),
    h.table(["Metric", "Definition", "What it tests"], [
      ["Time to alert (MTTD)", "Prometheus alert start - fault time", "SLI + alert rule design"],
      ["Time to engage", "Incident opened (page received) - fault time", "Alertmanager routing + webhook"],
      ["Time to recover (MTTR)", "Sustained healthy traffic - fault time", "The whole loop, including the fix"],
    ], [2, 3.2, 2.4]),
    h.spacer(),

    h.H2("6.6 Error budget on the dashboard"),
    h.P("The On-call page shows the SLO over the last minute, the burn rate, and the 24-hour error budget: at " +
      "2 requests/s a day has 172,800 requests, so the budget is 1,728 bad requests. Every incident visibly " +
      "spends some of it, which is how real teams decide between shipping features and fixing reliability."),
    ...h.callout("explain", "If a teacher asks why the budget shows 0%", [
      "\"On the day of our experiments we broke the shop on purpose more than 60 times in a few hours, so the " +
      "budget is fully spent: that is the lab doing its job. In production, a spent error budget triggers an " +
      "error-budget policy, for example freezing risky releases until reliability recovers; adding that rule to " +
      "Jenkins is one of our future-work items.\"",
    ]),
  ];
};
