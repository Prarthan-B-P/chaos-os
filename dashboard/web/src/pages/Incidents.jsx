import React, { useEffect, useRef, useState } from "react";
import { api, fmtS, fmtTime, plain, POLICY_LABELS, useApi } from "../api.js";
import { Card, Loading, PageHead, Status } from "../components.jsx";

const selectedFromHash = () => Number(window.location.hash.split("/")[2]) || null;

function Symptoms({ s }) {
  if (!s || !Object.keys(s).length) return null;
  const items = [
    ["api", s.api_up ? "up" : "down"],
    ["errors", s.error_rate == null ? "–" : `${Math.round(s.error_rate * 100)}%`],
    ["p95", s.p95_ms == null ? "–" : `${Math.round(s.p95_ms)} ms`],
    ["redis", s.redis_ok == null ? "?" : `${s.redis_ok ? "ok" : "unreachable"} ${Math.round(s.redis_ms ?? 0)} ms`],
    ["postgres", s.postgres_ok == null ? "?" : `${s.postgres_ok ? "ok" : "unreachable"} ${Math.round(s.postgres_ms ?? 0)} ms`],
  ];
  return <div className="symptoms">{items.map(([k, v]) => <span key={k} className="pill">{k}: {v}</span>)}</div>;
}

function PostMortem({ id, available }) {
  const [s, setS] = useState({ text: null, loading: false, error: null });
  useEffect(() => setS({ text: null, loading: false, error: null }), [id]);
  if (!available) return null;
  const load = () => {
    setS({ text: null, loading: true, error: null });
    api(`/insights/trial/${id}`).then((d) => setS({ text: plain(d.text), loading: false, error: null }))
      .catch((e) => setS({ text: null, loading: false, error: e.message }));
  };
  return (
    <div className="card ai-card" style={{ marginTop: 18, background: "var(--page)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <span className="eyebrow bracket">AI post-mortem</span>
        {!s.text && <button className="btn sm" onClick={load} disabled={s.loading}>{s.loading ? "Writing…" : "Write post-mortem"}</button>}
      </div>
      {s.loading && <><div className="shimmer" /><div className="shimmer" style={{ width: "50%" }} /></>}
      {s.error && <p className="error">{s.error}</p>}
      {s.text && <p className="prose" style={{ marginTop: 10 }}>{s.text}</p>}
    </div>
  );
}

function Detail({ id, llm }) {
  const { data: t, error } = useApi(`/trials/${id}`);
  if (!t) return <Card><Loading error={error} /></Card>;
  return (
    <Card>
      <div className="eyebrow bracket">Incident #{t.id}</div>
      <h2 style={{ marginTop: 8 }}>{t.scenario}</h2>
      <p className="sub mono">{fmtTime(t.started_at)} · {POLICY_LABELS[t.policy] || "Fixed action"}</p>
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginBottom: 20 }}>
        {t.recovered ? <Status ok label={`Recovered in ${fmtS(t.recovery_time_s)}`} /> : <Status label="Did not recover" />}
        <span className="kpi-note mono">detected after {fmtS(t.detected_after_s)}</span>
        <span className="kpi-note mono">{t.incident_failures}/{t.incident_requests} requests failed</span>
        {!t.valid && <Status warn label="invalid baseline" />}
      </div>
      <div className="timeline">
        <div className="t-item"><div className="t-title">Fault injected: <span className="mono">{t.scenario}</span></div><div className="t-meta">t = 0.0s</div></div>
        <div className="t-item"><div className="t-title">Outage detected</div><div className="t-meta">t = {fmtS(t.detected_after_s)}</div></div>
        {t.steps.map((s) => (
          <div key={s.id} className={`t-item ${!s.allowed ? "blocked" : s.healed ? "healed" : ""}`}>
            <div className="t-title">
              <span className="mono">{s.action}</span>
              {!s.allowed ? <Status label="blocked by safety validator" />
                : s.healed ? <Status ok label={`healed after ${fmtS(s.time_to_heal_s)}`} />
                  : <Status warn label="did not heal" />}
            </div>
            <div className="t-meta">
              {s.allowed ? `t = ${fmtS(s.started_s)} · ran ${fmtS(s.duration_s)} · reward ${s.reward?.toFixed(2)} · ` : ""}{s.verdict}
            </div>
            {s.note && <div className="t-meta" style={{ fontStyle: "italic" }}>“{s.note}”</div>}
            <Symptoms s={s.symptoms} />
          </div>
        ))}
        <div className={`t-item ${t.recovered ? "healed" : "blocked"}`}>
          <div className="t-title">{t.recovered ? "Sustained recovery confirmed" : "Timed out"}</div>
          <div className="t-meta">{t.recovered ? `t = ${fmtS(t.recovery_time_s)}` : "service still unhealthy"}</div>
        </div>
      </div>
      <PostMortem id={t.id} available={llm} />
    </Card>
  );
}

export default function Incidents({ go }) {
  const { data, error } = useApi("/trials?limit=300", 15000);
  const { data: overview } = useApi("/overview");
  const [selected, setSelected] = useState(selectedFromHash);
  const [filter, setFilter] = useState("all");
  const selectedRow = useRef(null);

  useEffect(() => {
    const onHash = () => setSelected(selectedFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => { selectedRow.current?.scrollIntoView({ block: "nearest" }); }, [selected, data]);
  if (!data) return <Loading error={error} />;

  const rows = data.filter((t) => filter === "all" || (t.policy || "fixed") === filter);
  const policies = [...new Set(data.map((t) => t.policy || "fixed"))];
  const open = (id) => go(`incidents/${id}`);

  return (
    <>
      <PageHead eyebrow="Incidents" title="Every experiment, step by step."
                right={<select className="select" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by responder">
                  <option value="all">All responders</option>
                  {policies.map((p) => <option key={p} value={p}>{POLICY_LABELS[p] || p}</option>)}
                </select>}>
        What was observed, what each step did, what the safety validator allowed, and how it ended.
      </PageHead>
      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <section className="card table-scroll" style={{ padding: "0 12px" }}>
          <table>
            <thead><tr><th>#</th><th>Failure</th><th>Responder</th><th>Actions</th><th>Outcome</th></tr></thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id} ref={selected === t.id ? selectedRow : null} tabIndex={0}
                    className={`clickable ${selected === t.id ? "selected" : ""}`}
                    onClick={() => open(t.id)} onKeyDown={(e) => e.key === "Enter" && open(t.id)}>
                  <td className="mono">{t.id}</td>
                  <td className="mono" style={{ color: "var(--ink)" }}>{t.scenario}</td>
                  <td>{POLICY_LABELS[t.policy] || "Fixed action"}</td>
                  <td className="mono">{t.actions || t.action}{t.safety_blocked ? ` +${t.safety_blocked} blocked` : ""}</td>
                  <td>{t.recovered ? <Status ok label={fmtS(t.recovery_time_s)} /> : <Status label="no recovery" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <div style={{ position: "sticky", top: 84 }}>
          {selected ? <Detail id={selected} llm={overview?.llm_available} />
            : <Card><div className="empty">Select an incident to see its timeline.</div></Card>}
        </div>
      </div>
    </>
  );
}
