import React, { useState } from "react";
import { api, useApi } from "../api.js";
import { Card, Icon, Loading, PageHead, Status } from "../components.jsx";

export default function Safety({ go }) {
  const { data, error } = useApi("/safety", 15000);
  const [err, setErr] = useState(null);
  if (!data) return <Loading error={error} />;
  const { policy, blocked } = data;
  const redTeam = () => {
    setErr(null);
    api("/jobs", { method: "POST", body: JSON.stringify({ scenario: "redis_down", policy: "adversarial", reps: 1, timeout_s: 60 }) })
      .then(() => go("run")).catch((e) => setErr(e.message));
  };

  return (
    <>
      <PageHead eyebrow="Safety" title="Guardrails first."
                right={<button className="btn primary" onClick={redTeam}>Run red-team test <Icon name="arrow" /></button>}>
        Every proposal — from rules, the learned bandit or the LLM — is checked against <span className="mono">safety-policy.yml</span> before
        it runs. The Ansible playbooks enforce a second, independent allowlist. The red-team test proposes unsafe actions on purpose.
      </PageHead>
      {err && <p className="error">{err}</p>}
      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <Card title="Approved actions" sub="Impact level and the cost charged to the learning reward">
          <table>
            <thead><tr><th>Action</th><th>Impact</th><th className="num">Cost</th></tr></thead>
            <tbody>
              {Object.entries(policy.actions).map(([name, a]) => (
                <tr key={name}>
                  <td className="mono" style={{ color: "var(--ink)" }}>{name}</td>
                  <td><span className={`tag ${a.impact === "high" ? "held" : ""}`}>{a.impact}{a.impact === "high" ? " · needs approval" : ""}</span></td>
                  <td className="mono num">{a.cost.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Rules">
          <div className="grid" style={{ gap: 14 }}>
            <Status ok label={`Only approved labs: ${policy.environment.allowed_projects.join(", ")}`} />
            <Status ok label={`At most ${policy.limits.max_actions_per_incident} actions per incident`} />
            <Status ok label="No action repeats within an incident (no restart loops)" />
            <Status ok label={`High-impact approval mode: ${policy.approval.high_impact}`} />
            <Status ok label="Unknown actions are always rejected" />
          </div>
        </Card>
      </div>
      <Card title="Blocked proposals" sub="Actions the validator refused. None of these ran.">
        {blocked.length === 0 ? <div className="empty">Nothing blocked yet. Run the red-team test to exercise the guardrails.</div> : (
          <table>
            <thead><tr><th>Proposed action</th><th>Reason</th></tr></thead>
            <tbody>
              {blocked.map((b) => (
                <tr key={b.id}><td className="mono" style={{ color: "var(--ink)" }}>{b.action}</td><td><Status label={b.verdict} /></td></tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
