import React, { useEffect, useRef, useState } from "react";
import { api, POLICY_LABELS, useApi } from "../api.js";
import { Card, Icon, Loading, PageHead, Status } from "../components.jsx";

const EVENT_TEXT = {
  reset: () => "Resetting lab to a known-good state",
  warmup: (e) => `Warming up under load (${e.seconds}s baseline)`,
  injected: (e) => `FAULT INJECTED: ${e.scenario}`,
  detected: (e) => `Outage detected after ${e.after_s}s`,
  action: (e) => `> ${e.action} — ${e.verdict}`,
  blocked: (e) => `BLOCKED ${e.action}: ${e.reason}`,
  step_done: (e) => `${e.action}: ${e.healed ? "service healed" : "no improvement"}`,
  done: (e) => (e.recovered ? `RECOVERED in ${e.recovery_time_s}s` : "DID NOT RECOVER"),
};

export default function Run({ go }) {
  const { data: o, error } = useApi("/overview");
  const { data: job } = useApi("/jobs/current", 1000);
  const [form, setForm] = useState({ scenario: "redis_down", mode: "policy", policy: "heuristic", action: "cache_bypass", reps: 1 });
  const [err, setErr] = useState(null);
  const logRef = useRef(null);
  const eventCount = job?.events?.length ?? 0;

  useEffect(() => {  // keep the live log scrolled to the newest event
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [eventCount]);
  if (!o) return <Loading error={error} />;

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const running = job?.state === "running";
  const unavailable = (p) => (p === "llm" && !o.llm_available) || (p === "bandit" && !o.model_trained);
  const start = () => {
    setErr(null);
    const reps = Math.min(5, Math.max(1, Number(form.reps) || 1));
    const body = { scenario: form.scenario, reps, timeout_s: 90,
                   ...(form.mode === "policy" ? { policy: form.policy } : { action: form.action }) };
    api("/jobs", { method: "POST", body: JSON.stringify(body) }).catch((e) => setErr(e.message));
  };

  return (
    <>
      <PageHead eyebrow="Run" title="Break it on purpose.">
        Inject a failure into the live lab and watch a responder handle it. One experiment runs at a time, and every
        action still passes the safety validator.
      </PageHead>
      <div className="grid grid-3-1" style={{ alignItems: "start" }}>
        <Card title="Live progress"
              sub={running ? `Repetition ${job.rep} of ${job.request.reps}` : job?.state === "done" ? "Finished" : job?.state === "error" ? "Stopped" : "Idle"}>
          {eventCount ? (
            <div className="log" ref={logRef}>
              {job.events.map((e, i) => (
                <div key={i}><span className="t">{e.t.toFixed(1).padStart(6)}s </span>{(EVENT_TEXT[e.kind] || (() => e.kind))(e)}</div>
              ))}
            </div>
          ) : <div className="empty">Nothing running. Pick a failure and a responder, then start.</div>}
          {job?.state === "error" && <p className="error">{job.error}</p>}
          {job?.trial_ids?.length > 0 && (
            <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {job.trial_ids.map((id) => <button key={id} className="btn sm" onClick={() => go(`incidents/${id}`)}>Incident #{id} →</button>)}
            </div>
          )}
        </Card>

        <Card title="Experiment">
          <div className="grid" style={{ gap: 16 }}>
            <div className="field">
              <label htmlFor="scenario">Failure to inject</label>
              <select id="scenario" value={form.scenario} onChange={set("scenario")}>
                <optgroup label="Training failures">
                  {o.scenarios.filter((s) => !s.held_out).map((s) => <option key={s.name} value={s.name}>{s.name} — {s.description}</option>)}
                </optgroup>
                <optgroup label="Held-out failures">
                  {o.scenarios.filter((s) => s.held_out).map((s) => <option key={s.name} value={s.name}>{s.name} — {s.description}</option>)}
                </optgroup>
              </select>
            </div>
            <div className="seg" role="tablist" aria-label="Who decides">
              <button className={form.mode === "policy" ? "on" : ""} onClick={() => setForm({ ...form, mode: "policy" })}>Policy decides</button>
              <button className={form.mode === "action" ? "on" : ""} onClick={() => setForm({ ...form, mode: "action" })}>Fixed action</button>
            </div>
            {form.mode === "policy" ? (
              <div className="field">
                <label htmlFor="policy">Responder</label>
                <select id="policy" value={form.policy} onChange={set("policy")}>
                  {o.policies.map((p) => (
                    <option key={p.name} value={p.name} disabled={unavailable(p.name)}>
                      {POLICY_LABELS[p.name] || p.name}{unavailable(p.name) ? " (unavailable)" : ""}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="field">
                <label htmlFor="action">Action</label>
                <select id="action" value={form.action} onChange={set("action")}>
                  {o.actions.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
                </select>
              </div>
            )}
            <div className="field">
              <label htmlFor="reps">Repetitions (1–5)</label>
              <input id="reps" type="number" min="1" max="5" value={form.reps} onChange={set("reps")} />
            </div>
            <button className="btn primary" onClick={start} disabled={running}>
              {running ? "Running…" : <>Start experiment <Icon name="arrow" /></>}
            </button>
            {err && <Status label={err} />}
          </div>
        </Card>
      </div>
    </>
  );
}
