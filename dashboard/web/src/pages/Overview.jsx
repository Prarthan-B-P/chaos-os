import React, { useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  api, fmtPct, fmtS, fmtTime, LINKS, plain, POLICY_COLORS, POLICY_LABELS, POLICY_ORDER, useApi, useLab,
} from "../api.js";
import { Icon, LeaderCard, Loading, Status } from "../components.jsx";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const SUGGESTIONS = [
  "Which fix works best for a slow database?",
  "Did the bandit beat the hand-written rules?",
  "Why does restarting Redis fail on latency?",
];
const axis = { stroke: "var(--axis)", tick: { fill: "var(--muted)", fontSize: 11, fontFamily: "var(--mono)" }, tickLine: false };
const median = (xs) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
};

/* ---------------------------------------------------------------- hero */

function Hero({ o, trials, go }) {
  const policyRuns = trials.filter((t) => t.valid && POLICY_ORDER.includes(t.policy));
  const recovered = policyRuns.filter((t) => t.recovered);
  const fixed = trials.filter((t) => t.policy === "fixed" || !t.policy).length;
  return (
    <section className="container hero">
      <div>
        <div className="eyebrow bracket">Resilience lab</div>
        <h1 className="display">break it.<br />learn from it<em>.</em></h1>
        <p className="lead">
          Faults injected into a live shop under load, recovery actions chosen by competing
          policies, every outcome timed request by request.
        </p>
        <div className="hero-actions">
          <button className="btn primary" onClick={() => go("run")}>Run experiment <Icon name="arrow" /></button>
          <button className="btn" onClick={() => document.getElementById("ask-input")?.focus()}>Ask the lab</button>
        </div>
      </div>
      <div className="stat-col">
        <div>
          <div className="eyebrow">Experiments run</div>
          <div className="stat-num">{o.trials}</div>
          <p>{policyRuns.length} policy-driven incidents and {fixed} fixed-action trials across {o.scenarios.length} failure types.</p>
        </div>
        <div>
          <div className="eyebrow">Policy recovery rate</div>
          <div className="stat-num">
            {policyRuns.length ? Math.round((100 * recovered.length) / policyRuns.length) : "–"}<small>%</small>
          </div>
          <p>Median {fmtS(median(recovered.map((t) => t.recovery_time_s)))} from fault injection to 5 s of sustained healthy traffic.</p>
        </div>
        <div>
          <div className="eyebrow">Unsafe actions blocked</div>
          <div className="stat-num">{o.safety_blocked}</div>
          <p>Every proposal passes the safety validator before it runs. None of these executed.</p>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- ask the lab */

function Ask({ available }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [listening, setListening] = useState(false);
  const [micError, setMicError] = useState(null);
  const requestId = useRef(0);

  const ask = (text) => {
    const q = text.trim();
    if (!q) return;
    const id = ++requestId.current;  // ignore replies to questions that were closed or replaced
    setQuestion(q);
    setAnswer({ q, loading: true });
    api("/ask", { method: "POST", body: JSON.stringify({ question: q }) })
      .then((d) => { if (id === requestId.current) setAnswer({ q, text: plain(d.text) }); })
      .catch((e) => { if (id === requestId.current) setAnswer({ q, error: e.message }); });
  };
  const close = () => { requestId.current += 1; setAnswer(null); };
  const listen = () => {
    setMicError(null);
    const rec = new SpeechRecognition();
    rec.lang = "en-US";
    rec.onresult = (e) => ask(e.results[0][0].transcript);
    rec.onerror = (e) => { setListening(false); setMicError(`Microphone unavailable (${e.error}).`); };
    rec.onend = () => setListening(false);
    setListening(true);
    rec.start();
  };

  return (
    <section className="section">
      <div className="container">
        <div className="section-head">
          <div>
            <div className="eyebrow bracket">Ask the lab</div>
            <h2 className="section-title">Questions, answered from measured data.</h2>
          </div>
          <span className="ai-badge">gpt-4o-mini</span>
        </div>
        <form className="askbar" onSubmit={(e) => { e.preventDefault(); ask(question); }}>
          <span className="prompt" aria-hidden="true">›</span>
          <input id="ask-input" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={500}
                 placeholder={available ? "e.g. which fix works best for a slow database?" : "Add OPENAI_API_KEY to .env to enable the lab assistant"}
                 aria-label="Ask the lab a question" disabled={!available} />
          {SpeechRecognition && available && (
            <button type="button" className={`icon-btn ${listening ? "listening" : ""}`} onClick={listen}
                    aria-label="Ask by voice" title="Ask by voice"><Icon name="mic" /></button>
          )}
          <button type="submit" className="btn primary" disabled={!available || !question.trim()}>Ask <Icon name="arrow" /></button>
        </form>
        {micError && <p className="error" style={{ fontSize: 13 }}>{micError}</p>}
        <div className="chips">
          {SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => ask(s)} disabled={!available}>{s}</button>)}
        </div>
        {answer && (
          <div className="answer" aria-live="polite">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="eyebrow bracket">Answer</span>
              <button className="icon-btn" style={{ width: 32, height: 32 }} onClick={close} aria-label="Close answer"><Icon name="x" /></button>
            </div>
            <div className="q">› {answer.q}</div>
            {answer.loading && <><div className="shimmer" /><div className="shimmer" style={{ width: "45%" }} /></>}
            {answer.error && <p className="error">{answer.error}</p>}
            {answer.text && <p className="prose" style={{ color: "var(--ink)" }}>{answer.text}</p>}
          </div>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- leaderboard */

function Board({ o, matrix, policies, go }) {
  const hasPolicies = policies.some((r) => POLICY_ORDER.includes(r.policy));
  const [mode, setMode] = useState(null);
  const [set, setSet] = useState("training");
  const shown = mode ?? (hasPolicies ? "policy" : "action");
  const scenarios = o.scenarios.filter((s) => (shown === "action" ? !s.held_out : (set === "held_out") === s.held_out));
  const rows = shown === "policy" ? policies.filter((r) => POLICY_ORDER.includes(r.policy)) : matrix;

  return (
    <section className="section">
      <div className="container">
        <div className="section-head">
          <div>
            <div className="eyebrow bracket">Leaderboard</div>
            <h2 className="section-title">Which responder recovers fastest?</h2>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <div className="seg" role="tablist" aria-label="Responders">
              <button className={shown === "policy" ? "on" : ""} onClick={() => setMode("policy")}>Policies</button>
              <button className={shown === "action" ? "on" : ""} onClick={() => setMode("action")}>Fixed actions</button>
            </div>
            {shown === "policy" && (
              <div className="seg" role="tablist" aria-label="Failure set">
                <button className={set === "training" ? "on" : ""} onClick={() => setSet("training")}>Training</button>
                <button className={set === "held_out" ? "on" : ""} onClick={() => setSet("held_out")}>Held-out</button>
              </div>
            )}
          </div>
        </div>
        <div className="grid grid-3">
          {scenarios.map((s) => (
            <LeaderCard key={s.name} scenario={s} rows={rows} keyField={shown} onOpen={() => go("incidents")} />
          ))}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------- lab + learning */

function LabPanel() {
  const { data: lab, reload } = useLab();
  const [state, setState] = useState({ busy: false, error: null });
  const reset = () => {
    setState({ busy: true, error: null });
    api("/lab/reset", { method: "POST" })
      .then(() => setState({ busy: false, error: null }))
      .catch((e) => setState({ busy: false, error: e.message }))
      .finally(reload);
  };
  if (!lab) return <section className="card"><Loading /></section>;
  const faults = lab.proxies.filter((p) => !p.enabled || p.toxics.length);
  return (
    <section className="card">
      <div className="section-head" style={{ marginBottom: 14 }}>
        <div>
          <div className="eyebrow bracket">Live lab</div>
          <h3 style={{ marginTop: 8 }}>{lab.services.length} services · project chaosos</h3>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn sm" onClick={reset} disabled={state.busy}>{state.busy ? "Resetting…" : "Reset lab"}</button>
          <a className="btn sm" href={LINKS.grafana} target="_blank" rel="noreferrer">Grafana <Icon name="external" /></a>
        </div>
      </div>
      {state.error && <p className="error" style={{ fontSize: 13 }}>{state.error}</p>}
      <div className="table-wrap"><table>
        <thead><tr><th>Service</th><th>State</th><th>Uptime</th></tr></thead>
        <tbody>
          {lab.services.map((s) => (
            <tr key={s.name}>
              <td className="mono" style={{ color: "var(--ink)" }}>{s.name}</td>
              <td><Status ok={s.state === "running"} label={s.state} /></td>
              <td className="mono">{s.status.replace(/\s*\(.*\)/, "")}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <div style={{ marginTop: 14 }}>
        {faults.length === 0 ? <Status ok label="No faults injected" />
          : faults.map((f) => <div key={f.proxy}><Status warn label={`${f.proxy}: ${f.enabled ? f.toxics.join(", ") : "connection cut"}`} /></div>)}
      </div>
    </section>
  );
}

function LearningPanel({ curve, go }) {
  if (!curve || curve.steps === 0) {
    return <section className="card"><div className="eyebrow bracket">Learning</div><div className="empty">Needs training data</div></section>;
  }
  const last = curve.curve.at(-1);
  return (
    <section className="card">
      <div className="section-head" style={{ marginBottom: 6 }}>
        <div>
          <div className="eyebrow bracket">Learning</div>
          <div className="stat-num" style={{ marginBottom: 0 }}>{fmtPct(last.accuracy)}</div>
          <div className="kpi-note">bandit picks the best measured action after {last.steps_seen} logged steps</div>
        </div>
        <button className="link" onClick={() => go("learning")}>Details →</button>
      </div>
      <div className="legend" style={{ marginTop: 10 }}>
        <span><i style={{ background: POLICY_COLORS.bandit }} />Bandit</span>
        {Object.keys(curve.baselines).map((k) => <span key={k}><i style={{ background: POLICY_COLORS[k] }} />{POLICY_LABELS[k]} (fixed)</span>)}
      </div>
      <div style={{ height: 300 }}>
        <ResponsiveContainer>
          <LineChart data={curve.curve} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="steps_seen" {...axis} />
            <YAxis {...axis} axisLine={false} domain={[0, 1]} tickFormatter={fmtPct} width={42} />
            <Tooltip formatter={(v) => fmtPct(v)} labelFormatter={(l) => `${l} steps seen`}
                     contentStyle={{ border: "1px solid var(--line-strong)", borderRadius: 0, fontFamily: "var(--mono)", fontSize: 12 }} />
            {Object.entries(curve.baselines).map(([k, b]) => (
              <ReferenceLine key={k} y={b.accuracy} stroke={POLICY_COLORS[k]} strokeDasharray="4 4" strokeWidth={1.5} />
            ))}
            <Line type="monotone" dataKey="accuracy" name="Bandit" stroke={POLICY_COLORS.bandit} strokeWidth={2}
                  dot={{ r: 3.5, strokeWidth: 2, stroke: "#fff" }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------- incidents */

function RecentIncidents({ trials, go }) {
  const rows = trials.slice(0, 8);
  const open = (id) => go(`incidents/${id}`);
  return (
    <section className="section">
      <div className="container">
        <div className="section-head">
          <div>
            <div className="eyebrow bracket">Incidents</div>
            <h2 className="section-title">Latest incidents</h2>
          </div>
          <button className="link" onClick={() => go("incidents")}>View all incidents →</button>
        </div>
        <div className="card table-wrap" style={{ padding: "4px 12px" }}>
          <table>
            <thead><tr><th>#</th><th>Failure</th><th>Responder</th><th>Actions</th><th>Outcome</th><th className="num">Failed req</th><th>When</th></tr></thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id} className="clickable" tabIndex={0} onClick={() => open(t.id)}
                    onKeyDown={(e) => e.key === "Enter" && open(t.id)}>
                  <td className="mono">{t.id}</td>
                  <td className="mono" style={{ color: "var(--ink)" }}>{t.scenario}</td>
                  <td>{POLICY_LABELS[t.policy] || "Fixed action"}</td>
                  <td className="mono">{t.actions || t.action}{t.safety_blocked ? ` +${t.safety_blocked} blocked` : ""}</td>
                  <td>{t.recovered ? <Status ok label={fmtS(t.recovery_time_s)} /> : <Status label="no recovery" />}</td>
                  <td className="mono num">{t.incident_failures}</td>
                  <td className="mono">{fmtTime(t.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- AI analysis */

function Analysis({ available }) {
  const [state, setState] = useState({ paras: [], loading: false, error: null });
  const load = (refresh = false) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    api(`/insights/results${refresh ? "?refresh=true" : ""}`)
      .then((d) => setState({ paras: plain(d.text).split(/\n\s*\n/).filter((p) => p.trim()), loading: false, error: null }))
      .catch((e) => setState({ paras: [], loading: false, error: e.message }));
  };
  useEffect(() => { if (available) load(); }, [available]);

  return (
    <section className="section">
      <div className="container">
        <div className="section-head">
          <div>
            <div className="eyebrow bracket">AI analysis</div>
            <h2 className="section-title">What the data says.</h2>
          </div>
          {available && (
            <button className="btn sm" onClick={() => load(true)} disabled={state.loading}>
              <Icon name="refresh" /> {state.loading ? "Writing…" : "Regenerate"}
            </button>
          )}
        </div>
        {!available && <p className="muted">Add your OpenAI key to <span className="mono">.env</span> to enable AI analysis (gpt-4o-mini).</p>}
        {state.loading && !state.paras.length && <><div className="shimmer" /><div className="shimmer" style={{ width: "50%" }} /></>}
        {state.error && <p className="error">{state.error}</p>}
        {state.paras.length > 0 && (
          <div className="grid grid-3">
            {state.paras.slice(0, 3).map((p, i) => (
              <div key={i}>
                <div className="eyebrow">{String(i + 1).padStart(2, "0")}</div>
                <p className="prose" style={{ marginTop: 8 }}>{p}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------- page */

export default function Overview({ go }) {
  const { data: o, error } = useApi("/overview", 10000);
  const { data: trials } = useApi("/trials?limit=200", 10000);
  const { data: matrix } = useApi("/matrix", 30000);
  const { data: policies } = useApi("/policies", 30000);
  const { data: curve } = useApi("/learning-curve", 60000);
  const ready = useMemo(() => o && trials && matrix && policies, [o, trials, matrix, policies]);

  if (!ready) return <div className="container main"><Loading error={error} /></div>;
  return (
    <>
      <Hero o={o} trials={trials} go={go} />
      <Ask available={o.llm_available} />
      <Board o={o} matrix={matrix} policies={policies} go={go} />
      <section className="section">
        <div className="container grid grid-2">
          <LabPanel />
          <LearningPanel curve={curve} go={go} />
        </div>
      </section>
      <RecentIncidents trials={trials} go={go} />
      <Analysis available={o.llm_available} />
    </>
  );
}
