import React, { useEffect, useState } from "react";
import { api, fmtPct, fmtS, fmtTime, plain, POLICY_LABELS, useApi, useLab } from "../api.js";
import { Card, Icon, Loading, PageHead, Status, Trail } from "../components.jsx";

const pct1 = (x) => (x == null ? "–" : `${(x * 100).toFixed(x >= 0.999 || x < 0.1 ? 1 : 0)}%`);

const STEP_TEXT = {
  alert: (e) => `Paged by Alertmanager: ${e.name}`,
  confirmed: (e) => `Confirmed with live probe traffic: ${fmtPct(e.error_rate)} errors, p95 ${e.p95_ms ?? "–"} ms`,
  fallback: (e) => `${POLICY_LABELS[e.policy] || e.policy} unavailable (${e.reason}); using ${e.using}`,
  approval: (e) => `${e.action} is high impact: waiting for a human decision`,
  approved: (e) => `${e.action} approved by ${e.by}`,
  denied: (e) => `${e.action} denied by ${e.by}`,
  expired: (e) => `No decision on ${e.action} within ${e.timeout_s}s: not run (fail safe)`,
  blocked: (e) => `Blocked ${e.action}: ${e.reason}`,
  action: (e) => `Running ${e.action} via Ansible (${e.verdict})`,
  step_done: (e) => `${e.action}: ${e.healed ? "service healed" : "no improvement"}`,
  resolved: (e) => `Mitigated: 5 s of healthy traffic, ${e.mitigation_s}s after the page`,
  escalated: (e) => `Escalated to a human: ${e.reason}`,
  closed: (e) => `Closed: ${e.why}`,
};
const CLASS = { blocked: "blocked", denied: "blocked", expired: "blocked", escalated: "blocked", resolved: "healed" };

const STATUS = {
  investigating: ["Investigating", true, true],
  awaiting_approval: ["Waiting for you", false, true],
  resolved: ["Mitigated", true, false],
  escalated: ["Escalated", false, false],
};

function IncidentStatus({ status, closed }) {
  const [label, ok, warn] = STATUS[status] || [status, false, true];
  return <Status ok={ok} warn={warn && !ok} label={status === "escalated" && closed ? "Escalated · recovered later" : label} pulse={status === "investigating"} />;
}

function Timeline({ events }) {
  return (
    <div className="timeline">
      {events.map((e, i) => (
        <div key={i} className={`t-item ${CLASS[e.kind] || ""}`}>
          <div className="t-title">{(STEP_TEXT[e.kind] || (() => e.kind))(e)}</div>
          {e.t != null && <div className="t-meta">+{e.t.toFixed(1)}s</div>}
        </div>
      ))}
    </div>
  );
}

function Approval({ approval, actions, onDone }) {
  const left = () => Math.max(0, Math.round((new Date(approval.expires_at) - Date.now()) / 1000));
  const [secs, setSecs] = useState(left);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const id = setInterval(() => setSecs(left()), 500);
    return () => clearInterval(id);
  }, [approval.expires_at]);  // eslint-disable-line react-hooks/exhaustive-deps

  const decide = (approve) => {
    setBusy(true);
    setErr(null);
    api(`/oncall/approvals/${approval.id}`, { method: "POST", body: JSON.stringify({ approve }) })
      .then(onDone).catch((e) => setErr(e.message)).finally(() => setBusy(false));
  };
  const s = approval.symptoms || {};
  return (
    <section className="card approval" role="alertdialog" aria-labelledby="approval-title" aria-describedby="approval-why">
      <div className="eyebrow bracket">Approval needed · incident #{approval.incident_id}</div>
      <h2 id="approval-title">Run <span className="mono">{approval.action}</span>?</h2>
      <p id="approval-why">
        {actions[approval.action] || approval.action}. Marked <b>high impact</b> in safety-policy.yml, so the agent
        will not run it without you.{approval.note ? ` The responder's reason: “${approval.note}”` : ""}
      </p>
      <div className="symptoms">
        <span className="pill">errors {fmtPct(s.error_rate)}</span>
        <span className="pill">p95 {s.p95_ms == null ? "–" : `${Math.round(s.p95_ms)} ms`}</span>
        <span className="pill">api {s.api_up ? "up" : "down"}</span>
        <span className="pill">redis {s.redis_ok == null ? "?" : s.redis_ok ? "ok" : "failing"}</span>
        <span className="pill">postgres {s.postgres_ok == null ? "?" : s.postgres_ok ? "ok" : "failing"}</span>
      </div>
      <div className="approval-actions">
        <button className="btn accent" onClick={() => decide(true)} disabled={busy}>Approve</button>
        <button className="btn" onClick={() => decide(false)} disabled={busy}>Deny</button>
        <span className="mono muted" aria-live="polite">{secs}s left · no answer = not run</span>
      </div>
      {err && <p className="error">{err}</p>}
    </section>
  );
}

function Kpi({ label, value, note, children }) {
  return (
    <Card>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {children}
      {note && <div className="kpi-note">{note}</div>}
    </Card>
  );
}

function Postmortem({ incident, llm }) {
  const [text, setText] = useState(incident.postmortem);
  const [state, setState] = useState({ busy: false, err: null });
  useEffect(() => setText(incident.postmortem), [incident.id, incident.postmortem]);
  const write = () => {
    setState({ busy: true, err: null });
    api(`/insights/oncall/${incident.id}?refresh=${text ? "true" : "false"}`)
      .then((d) => { setText(d.text); setState({ busy: false, err: null }); })
      .catch((e) => setState({ busy: false, err: e.message }));
  };
  return (
    <Card className="ai-card" title="Post-mortem" right={<span className="ai-badge">gpt-4o-mini</span>}
          sub="Written from the incident record only. The agent was never told what failed.">
      {state.busy ? <><div className="shimmer" /><div className="shimmer" style={{ width: "55%" }} /></>
        : text ? <p className="prose">{plain(text)}</p>
          : <div className="empty">{llm ? "No post-mortem yet." : "Add an OpenAI key to .env to get AI post-mortems."}</div>}
      {llm && !state.busy && <button className="link" onClick={write}><Icon name="refresh" />{text ? "Rewrite" : "Write post-mortem"}</button>}
      {state.err && <p className="error">{state.err}</p>}
    </Card>
  );
}

export default function OnCall() {
  const { data: d, error, reload } = useApi("/oncall", 2000);
  const lab = useLab();
  const [chosen, setChosen] = useState(null);
  const [target, setTarget] = useState("random");
  const [msg, setMsg] = useState(null);
  if (!d) return <Loading error={error} />;

  const save = (changes) => api("/oncall/settings", { method: "POST", body: JSON.stringify(changes) })
    .then(reload).catch((e) => setMsg({ err: e.message }));
  const breakIt = () => {
    setMsg({ text: "Injecting…" });
    api("/oncall/break", { method: "POST", body: JSON.stringify({ scenario: target }) })
      .then((r) => { setMsg({ text: `Injected ${r.scenario}. The agent was not told.` }); reload(); lab.reload(); })
      .catch((e) => setMsg({ err: e.message }));
  };

  const { slo, settings: cfg, agent, score } = d;
  const selected = d.incidents.find((i) => i.id === chosen) || null;
  const live = d.active;
  const burning = slo.burn_1m != null && slo.burn_1m >= slo.page_burn_rate;
  const llm = d.policies.find((p) => p.name === "llm")?.available;

  return (
    <>
      <PageHead eyebrow="On-call" title="It heals what nobody announced."
                right={<Status ok={agent.online && cfg.autopilot} warn={agent.online && !cfg.autopilot}
                               pulse label={!agent.online ? "Agent offline" : cfg.autopilot ? "Autopilot on" : "Autopilot off · watching only"} />}>
        An always-on agent guards the shop's SLO. When the error budget burns too fast, Prometheus pages it through
        Alertmanager. It confirms the page with its own probe traffic, picks a fix, passes the safety validator, and asks
        you before anything high impact. It never sees the chaos log.
      </PageHead>

      {d.approval && <Approval approval={d.approval} actions={d.actions} onDone={reload} />}

      <div className="grid grid-4">
        <Kpi label="SLO · last minute" value={pct1(slo.good_1m)}
             note={`of user requests good (target ${pct1(slo.target)})`}>
          {slo.good_1m != null && <Status ok={slo.good_1m >= slo.target} label={slo.good_1m >= slo.target ? "Within SLO" : "Breaching SLO"} />}
        </Kpi>
        <Kpi label="Burn rate · 1 min" value={slo.burn_1m == null ? "–" : `${slo.burn_1m.toFixed(1)}×`}
             note={`Pages at ${slo.page_burn_rate}× (1 min and 20 s windows)`}>
          {slo.burn_1m != null && <Status ok={!burning} warn={!burning && slo.burn_1m >= 1} label={burning ? "Paging" : slo.burn_1m >= 1 ? "Burning" : "Quiet"} />}
        </Kpi>
        <Kpi label="Error budget · 24 h" value={pct1(slo.budget_remaining == null ? null : Math.max(0, slo.budget_remaining))}
             note={slo.budget_allowed == null ? "Waiting for traffic data" : `${slo.budget_used} of ${slo.budget_allowed} bad requests used`} />
        <Kpi label="Unannounced faults healed" value={score.faults ? `${score.healed}/${score.faults}` : "–"}
             note={score.faults ? `median ${fmtS(score.median_recover_s)} from fault to healthy traffic` : "Break something to see the agent work"} />
      </div>

      <div className="grid grid-3-1" style={{ alignItems: "start" }}>
        <Card title={live ? `Incident #${live.id}` : "Live incident"}
              sub={live ? `${live.alert} · responder ${POLICY_LABELS[live.policy] || live.policy} · opened ${fmtTime(live.opened_at)}` : "Nothing open. The agent is watching the SLO."}
              right={live && <IncidentStatus status={live.status} closed={live.closed_at} />}>
          {live ? <Timeline events={live.timeline} /> : (
            <div className="empty">
              {d.chaos ? "A fault is active. Expect a page within about 20 seconds." : "All quiet."}
            </div>
          )}
        </Card>

        <Card title="Controls">
          <div className="grid" style={{ gap: 16 }}>
            <div className="field">
              <label>Autopilot</label>
              <div className="seg" role="group" aria-label="Autopilot">
                <button className={cfg.autopilot ? "on" : ""} aria-pressed={cfg.autopilot} onClick={() => save({ autopilot: true })}>On</button>
                <button className={!cfg.autopilot ? "on" : ""} aria-pressed={!cfg.autopilot} onClick={() => save({ autopilot: false })}>Off</button>
              </div>
            </div>
            <div className="field">
              <label htmlFor="oncall-policy">Responder</label>
              <select id="oncall-policy" value={cfg.policy} onChange={(e) => save({ policy: e.target.value })}>
                {d.policies.map((p) => (
                  <option key={p.name} value={p.name} disabled={!p.available}>
                    {POLICY_LABELS[p.name] || p.name}{p.available ? "" : " (unavailable)"}
                  </option>
                ))}
              </select>
            </div>
            <div className="divider-label">Chaos side · the agent is not told</div>
            <div className="field">
              <label htmlFor="oncall-fault">Failure</label>
              <select id="oncall-fault" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="random">Surprise me (random)</option>
                {d.scenarios.map((s) => <option key={s.name} value={s.name}>{s.name}{s.held_out ? " (held out)" : ""}</option>)}
              </select>
            </div>
            <button className="btn primary" onClick={breakIt}>Break it <Icon name="arrow" /></button>
            {d.chaos && <p className="kpi-note">Fault active: <span className="mono">{d.chaos.scenario}</span> · rolled back in {d.chaos.rollback_in_s}s</p>}
            {msg && (msg.err ? <Status label={msg.err} /> : <p className="kpi-note" aria-live="polite">{msg.text}</p>)}
            <div className="field">
              <label>Chaos monkey · a random fault every ~{cfg.monkey_every_min} min</label>
              <div className="seg" role="group" aria-label="Chaos monkey">
                <button className={cfg.monkey ? "on" : ""} aria-pressed={cfg.monkey} onClick={() => save({ monkey: true })}>On</button>
                <button className={!cfg.monkey ? "on" : ""} aria-pressed={!cfg.monkey} onClick={() => save({ monkey: false })}>Off</button>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <Card title="Scorecard" sub="Every unannounced fault, matched to the incident the agent opened for it.">
          {score.matches.length === 0 ? <div className="empty">No unannounced faults yet.</div> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Fault</th><th className="num">Alert</th><th className="num">Agent</th><th className="num">Healthy</th><th>Outcome</th></tr></thead>
                <tbody>
                  {score.matches.map((m) => (
                    <tr key={m.event.id}>
                      <td><span className="mono" style={{ color: "var(--ink)" }}>{m.event.scenario}</span><div className="t-meta">{m.event.source} · {fmtTime(m.event.at)}</div></td>
                      <td className="mono num">{m.detect_s == null ? "–" : `+${m.detect_s}s`}</td>
                      <td className="mono num">{m.engage_s == null ? "–" : `+${m.engage_s}s`}</td>
                      <td className="mono num">{m.recover_s == null ? "–" : `+${m.recover_s}s`}</td>
                      <td>{m.incident_id ? <button className="link" onClick={() => setChosen(m.incident_id)}><IncidentStatus status={m.status} /></button> : <span className="muted">no incident</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {score.faults > 0 && (
            <p className="kpi-note">Median time to alert {fmtS(score.median_detect_s)} · to healthy traffic {fmtS(score.median_recover_s)} · measured from the moment of injection.</p>
          )}
        </Card>

        <Card title="Active alerts" sub="From Alertmanager. Pages wake the agent; tickets are for humans.">
          {d.alerts == null ? <p className="error">Alertmanager is unreachable.</p>
            : d.alerts.length === 0 ? <div className="empty">No alerts firing.</div> : (
              <div className="grid" style={{ gap: 12 }}>
                {d.alerts.map((a) => (
                  <div key={`${a.name}-${a.started_at}`} className="alert-row">
                    <span className={`tag ${a.severity === "page" ? "accent" : ""}`}>{a.severity}</span>
                    <div><div style={{ fontWeight: 500 }}>{a.name}</div><div className="t-meta">{a.summary} · since {fmtTime(a.started_at)}</div></div>
                  </div>
                ))}
              </div>
            )}
        </Card>
      </div>

      <Card title="Incident history" sub="Click an incident for its timeline and post-mortem.">
        {d.incidents.length === 0 ? <div className="empty">No incidents yet.</div> : (
          <div className="table-wrap table-scroll">
            <table>
              <thead><tr><th>#</th><th>Opened</th><th>Alert</th><th>Responder</th><th>Actions</th><th>Outcome</th><th className="num">Mitigated in</th></tr></thead>
              <tbody>
                {d.incidents.map((i) => (
                  <tr key={i.id} className={`clickable ${chosen === i.id ? "selected" : ""}`} tabIndex={0}
                      onClick={() => setChosen(i.id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setChosen(i.id))}>
                    <td className="mono">{i.id}</td>
                    <td>{fmtTime(i.opened_at)}</td>
                    <td className="mono">{i.alert}</td>
                    <td>{POLICY_LABELS[i.policy] || i.policy}</td>
                    <td className="mono">{i.actions || "–"}{i.blocked && <span className="muted"> · blocked {i.blocked}</span>}</td>
                    <td><IncidentStatus status={i.status} closed={i.closed_at} /></td>
                    <td className="mono num">{fmtS(i.mitigation_s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selected && (
        <div className="grid grid-2" style={{ alignItems: "start" }}>
          <Card title={`Incident #${selected.id} timeline`} sub={`${selected.alert} · ${selected.probe_failures ?? 0} of ${selected.probe_requests ?? 0} probe requests failed while it was open`}
                right={<button className="icon-btn" onClick={() => setChosen(null)} aria-label="Close incident"><Icon name="x" /></button>}>
            <Timeline events={selected.timeline} />
            {selected.steps.filter((s) => s.trail?.length || s.note).map((s) => (
              <div key={s.step} className="step-why">
                <div className="t-meta">Step {s.step}: <span className="mono">{s.action}</span></div>
                {s.note && <div className="t-meta" style={{ fontStyle: "italic" }}>“{s.note}”</div>}
                <Trail trail={s.trail} />
              </div>
            ))}
          </Card>
          <Postmortem incident={selected} llm={llm} />
        </div>
      )}
    </>
  );
}
