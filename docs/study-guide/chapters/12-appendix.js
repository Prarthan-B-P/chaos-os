// Chapter 11: the most important files, read from the repository at build time.
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..", "..");

function file(rel, { from, to, maxLines = 70 } = {}) {
  const full = path.join(ROOT, rel);
  if (!fs.existsSync(full)) return [`[missing: ${rel}]`];
  let lines = fs.readFileSync(full, "utf8").replace(/\r/g, "").split("\n");
  if (from) {
    const i = lines.findIndex((l) => l.includes(from));
    if (i >= 0) lines = lines.slice(i);
  }
  if (to) {
    const j = lines.findIndex((l, k) => k > 0 && l.includes(to));
    if (j >= 0) lines = lines.slice(0, j);
  }
  if (lines.length > maxLines) lines = [...lines.slice(0, maxLines), "    ... (see the file for the rest)"];
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  return lines;
}

module.exports = (h) => [
  h.H1("12. Appendix: the key files, annotated"),
  h.Lead("These are the files teachers most often ask to see. They are copied here from the repository " +
    "when this guide is built, so they are always current."),

  h.H2("12.1 safety-policy.yml: the safety rules"),
  h.P("Read top to bottom: approved environments, the action budget, the approval modes (auto in the lab, " +
    "human on call), and for every action its impact and the cost charged in the bandit's reward."),
  ...h.code(file("safety-policy.yml")),

  h.H2("12.2 observability/prometheus/rules/slo.yml: SLO and alerts"),
  h.P("Four recording rules compute the bad-request ratio over 20 s, 1 min, 10 min and 1 h. The page needs " +
    "both the 1 min and 20 s ratios above 14.4%; the ticket needs 1 h and 10 min above 3%."),
  ...h.code(file("observability/prometheus/rules/slo.yml", { maxLines: 80 })),

  h.H2("12.3 observability/alertmanager/alertmanager.yml: routing pages to the agent"),
  ...h.code(file("observability/alertmanager/alertmanager.yml")),

  h.H2("12.4 resilience-gate.yml: what every release must survive"),
  ...h.code(file("resilience-gate.yml")),

  h.H2("12.5 ansible/playbooks/restart_service.yml: one recovery action"),
  h.P("Note the first task: the playbook refuses any service outside the allowlist, even if the validator " +
    "were bypassed."),
  ...h.code(file("ansible/playbooks/restart_service.yml")),

  h.H2("12.6 Jenkinsfile: the stages"),
  ...h.code(file("Jenkinsfile", { from: "stages {", to: "post {\n", maxLines: 90 })),

  h.H2("12.7 .trivyignore.yaml: accepted security risks, each with a reason"),
  ...h.code(file(".trivyignore.yaml")),
];
