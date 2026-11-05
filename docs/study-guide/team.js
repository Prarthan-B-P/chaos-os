// Builds the team roles guide:  node team.js  ->  CHAOS-OS-Team-Roles.docx
const fs = require("fs");
const path = require("path");
const { AlignmentType, Document, Footer, LevelFormat, Packer, PageNumber, Paragraph, TextRun } = require("docx");
const h = require("./lib");

const ROLES = [
  {
    who: "Member 1", title: "Architect and Measurement Lead",
    owns: "The problem statement, the architecture (11 services), how faults are injected, and how recovery is measured.",
    slot: "Opens the presentation (2 min) and hands over to Member 2.",
    demo: "Dashboard Overview and the Matrix page: every failure x every fix.",
    pitch: "\"Every system fails; the question is how fast it recovers. We built a lab of 11 containers: a web shop " +
      "with a Redis cache and a Postgres database, and Toxiproxy in between so we can inject real failures such as a " +
      "dead cache or a slow network. A load generator sends 20 requests a second and times every single one, and we " +
      "call the service recovered only after 5 straight healthy seconds at 99% success and under 300 milliseconds. " +
      "Our first finding: there is no universal fix. Each failure has its own best action, and a wrong one costs up " +
      "to 1,128 failed requests instead of about 30.\"",
    star: ["Systems fail and nobody measures whether runbooks work.",
      "Build a fair, precise way to inject failures and measure recovery.",
      "Docker Compose lab, Toxiproxy and docker-kill fault injection, open-model load generator, unit-tested recovery definition.",
      "Sub-second recovery measurement; proved each of 5 failures needs a different fix."],
    questions: ["How exactly do you define recovered?", "Why not measure recovery with Prometheus?",
      "Why does restarting Redis not fix Redis latency?", "Why Docker Compose and not Kubernetes?"],
    study: "Study guide chapters 1, 3, 4 · controller/chaosctl/analysis.py, experiment.py, scenarios.py · docker-compose.yml",
    handoff: "\"So we know which fix is right. But can a machine learn that by itself? Member 2.\"",
  },
  {
    who: "Member 2", title: "AI and Machine Learning Lead",
    owns: "The five responders: runbook, expert rules, the LinUCB bandit, gpt-4o-mini and the LLM agent with tools; the learning curve and the 56-trial ablation.",
    slot: "Second speaker (2 min).",
    demo: "Policies page, Learning page, and one LLM agent trial on the Incidents page with its tool trail.",
    pitch: "\"We compared five ways of deciding the fix. A classic runbook, 'restart whatever looks broken', was right " +
      "only 33% of the time. A contextual bandit, a small learning algorithm, learned from our experiment logs and " +
      "reached 88% with no hand-written rules, and it even solved a failure it had never seen, where the runbook " +
      "failed every time. We also tested gpt-4o-mini honestly with a 2 x 2 experiment: one paragraph of advice cut a " +
      "50-second recovery to 3 seconds but then made it skip a needed restart; giving it tools alone only made it " +
      "slower; tools plus advice was the most reliable. Lesson: test AI prompts like code.\"",
    star: ["Expert rules work but someone must study every new failure; LLM agents are hyped but untested.",
      "Find a responder that learns the right fix, and test what really helps an LLM.",
      "LinUCB bandit on 8 symptom features with a speed-minus-safety-cost reward; tool-using LLM agent; 2 x 2 ablation over 56 trials.",
      "Bandit 88% vs runbook 33%, 3/3 on an unseen failure; clear, honest LLM findings."],
    questions: ["Isn't the bandit memorising failure names?", "Why a bandit and not deep learning?",
      "Why gpt-4o-mini?", "Isn't the SRE advice just giving the LLM the answer?"],
    study: "Study guide chapters 5, 9.1-9.4 · controller/chaosctl/bandit.py, policies.py, agent.py, learning.py",
    handoff: "\"Smart decisions are dangerous without guardrails, and real failures are not announced. Member 3.\"",
  },
  {
    who: "Member 3", title: "Reliability (SRE) and Safety Lead",
    owns: "The safety validator and red team, SLOs and error budgets, burn-rate alerts, Alertmanager, and the on-call agent with human approval.",
    slot: "Third speaker (2 min) and runs the live Break-it demo.",
    demo: "On-call page: Break it (surprise), watch the incident timeline, then postgres_down and Approve; Grafana SLO row.",
    pitch: "\"Nothing runs without passing our safety shield: approved environment, an allowlist, no repeated actions, " +
      "at most three actions, and a human for risky ones. Our red-team policy tried drop_database; it was blocked, and " +
      "zero unsafe actions ever ran. Then we made it work like production: simulated users measure an SLO of 99% good " +
      "requests, Prometheus pages when the error budget burns 14 times too fast, and our on-call agent wakes up, " +
      "confirms the problem, fixes it, and asks me before restarting the database. In 21 surprise failures it healed " +
      "18 on its own in about 25 seconds, and handed the 3 unfixable ones to a human instead of looping.\"",
    star: ["Automation can make outages worse, and real failures are never announced.",
      "Make every action safe and heal unannounced failures like a human on-call engineer.",
      "YAML safety policy + Ansible allowlist + red team; SLI/SLO with multi-window burn-rate alerts (unit-tested); Alertmanager webhook; agent that confirms, fixes, asks for approval, escalates, writes post-mortems.",
      "0 unsafe actions; 18/21 surprise failures healed; median 11.8 s to alert, 25.8 s to healthy."],
    questions: ["What stops the AI from doing damage?", "What is an error budget and why 14.4?",
      "What if nobody approves?", "How do you know the agent did not cheat?"],
    study: "Study guide chapters 2.4-2.5, 4.6, 6 · safety-policy.yml · observability/prometheus/rules/slo.yml · controller/chaosctl/oncall.py, safety.py",
    handoff: "\"All of this has to ship safely, every time. Member 4.\"",
  },
  {
    who: "Member 4", title: "DevOps, Security and Delivery Lead",
    owns: "The Jenkins pipeline (10 stages), the resilience gate and demo bug, security scanning, Ansible, deployment (HTTPS, login, tunnel), and the start/share scripts.",
    slot: "Fourth speaker (2 min), closes, and leads the Q&A hand-offs.",
    demo: "Jenkins: main green vs demo branch red; the security report; share.bat public link.",
    pitch: "\"Every change goes through a 10-stage Jenkins pipeline: build, 45 unit tests, tests for our alert rules, a " +
      "security scan for leaked secrets and vulnerable packages, a real deployment, then a resilience gate that " +
      "injects six real failures and a surprise on-call drill. Our demo branch has a one-character bug that passes " +
      "unit and smoke tests, and only the resilience gate blocks it. The first security scan found real problems, " +
      "and we fixed them: upgraded packages, seven containers made non-root, 61 vulnerabilities removed from one image. " +
      "And it deploys anywhere with HTTPS and a login in one command, or shares from a laptop with one click.\"",
    star: ["Pipelines test code on a healthy system but never test recovery or security.",
      "Make resilience, alerting, security and on-call behaviour release gates.",
      "Jenkins multibranch job as code with isolated labs; gitleaks + Trivy + SBOMs; resilience gate; on-call drill; Caddy HTTPS deploy via Ansible; start/share scripts.",
      "Main passes in under 6 minutes; the one-character bug is blocked; 0 secrets, 61 to 0 CVEs in the frontend image."],
    questions: ["Walk me through the pipeline.", "What does the gate catch that tests miss?",
      "What did the security scan find?", "How is it deployed and secured?"],
    study: "Study guide chapters 7, 8 · Jenkinsfile · resilience-gate.yml · scripts/security-scan.sh · deploy/",
    handoff: "\"To sum up: we measure, learn, act safely, and block releases that cannot recover. Questions?\"",
  },
];

const roleSection = (r) => [
  h.H1(`${r.who}: ${r.title}`),
  h.table(["Role", "Details"], [["Owns", r.owns], ["Speaking slot", r.slot], ["Demo moment", r.demo], ["Study", r.study]], [1.4, 6]),
  ...h.callout("explain", "Your pitch (about 45 seconds)", [r.pitch]),
  h.H2("Your STAR story"),
  h.table(["STAR", "Your part"], [["**S**ituation", r.star[0]], ["**T**ask", r.star[1]], ["**A**ction", r.star[2]], ["**R**esult", r.star[3]]], [1.2, 6]),
  h.H2("Questions you answer first"),
  ...h.bullets(r.questions.map((q) => `${q} (model answers: study guide chapter 10)`)),
  ...h.callout("remember", "Your hand-off line", [r.handoff]),
];

const content = [
  new Paragraph({ spacing: { before: 1800 }, children: [new TextRun({ text: "CHAOS OS", bold: true, size: 80 })] }),
  new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: "Team roles and individual pitches", size: 32, color: h.C.accent })] }),
  h.P("Internal reference for our four-person team. Replace \"Member 1-4\" with names."),

  h.H1("How we divided the work, fairly"),
  ...h.bullets([
    "**Equal weight:** four roles of similar size, each with a clear part of the system, a demo moment and a 2-minute speaking slot.",
    "**Everyone owns something real:** each role maps to code and results you can open and explain, not just slides.",
    "**Nobody is a single point of failure:** every member also learns the shared basics below and can answer simple questions about any part.",
    "**Honest credit:** we say \"we built\" as a team. If asked about tools, we say plainly that we used AI assistants " +
    "(Claude for development help, gpt-4o-mini inside the project), and we only present what we understand and can explain ourselves.",
    "**Swap if it fits better:** match roles to interests (ML-minded person takes Member 2, ops-minded takes Member 4). Fairness matters more than the default order.",
  ]),
  h.table(["Member", "Role", "Speaks", "Demo"], ROLES.map((r) => [r.who, r.title, r.slot.split(" (")[0].replace(" and hands over to Member 2.", ""), r.demo.split(":")[0]]), [1.1, 2.6, 1.6, 2.6]),

  h.H1("What everyone must know (shared basics)"),
  ...h.bullets([
    "The 30-second pitch (pitch guide, section 1) and the real-world problem: long outages because the fix is a guess (MTTR).",
    "The architecture in one sentence: a web shop (API, Redis, Postgres) behind Toxiproxy, watched by Prometheus, fixed by policies through a safety validator and Ansible, gated by Jenkins.",
    "The five headline numbers: no universal fix; bandit 88% vs runbook 33%; 18/21 surprise failures healed; 0 unsafe actions; the gate blocks a one-character bug.",
    "The limitations: one laptop, small samples, the compound failure is unsolved.",
    "How to start it: start.bat (local) or share.bat (online link, login admin + password from deploy/secrets.yml).",
  ]),

  h.H1("Presentation running order (about 10 minutes + Q&A)"),
  h.table(["Time", "Who", "What"], [
    ["0:00", "Member 1", "Problem, architecture, measurement, result 1"],
    ["2:00", "Member 2", "Responders, bandit, LLM ablation"],
    ["4:00", "Member 3", "Safety, SLOs, on-call agent + live Break-it demo"],
    ["7:00", "Member 4", "Pipeline, gate demo (green vs red), security, deployment, summary"],
    ["9:30", "All", "Q&A: the owner answers first, anyone may add"],
  ], [0.8, 1.4, 5.5]),

  ...ROLES.flatMap(roleSection),

  h.H1("Rehearsal checklist"),
  ...h.bullets([
    "Run start.bat 10 minutes before; do one warm-up Break-it.",
    "Each member says their pitch out loud three times, under 60 seconds.",
    "Swap test: each member answers one question from another role.",
    "Backup plan: if the live demo fails, show the screenshots in the study guide.",
    "Fill names and college details in the paper's author block and the study guide cover.",
  ]),
];

const doc = new Document({
  creator: "CHAOS OS team", title: "CHAOS OS: team roles",
  styles: { default: {
    document: { run: { font: h.FONT, size: 22 } },
    heading1: { run: { font: h.FONT, size: 34, bold: true }, paragraph: { spacing: { before: 0, after: 200 }, keepNext: true, outlineLevel: 0 } },
    heading2: { run: { font: h.FONT, size: 26, bold: true, color: h.C.accent }, paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, outlineLevel: 1 } },
    heading3: { run: { font: h.FONT, size: 24, bold: true }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 2 } },
  } },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { margin: { top: 1300, bottom: 1300, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ children: ["CHAOS OS team roles · page ", PageNumber.CURRENT], size: 16, color: h.C.muted })] })] }) },
    children: content,
  }],
});

Packer.toBuffer(doc).then((b) => {
  fs.writeFileSync(path.join(__dirname, "CHAOS-OS-Team-Roles.docx"), b);
  console.log("wrote CHAOS-OS-Team-Roles.docx");
});
