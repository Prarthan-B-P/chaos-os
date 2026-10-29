import React, { useState } from "react";
import { fmtS, POLICY_COLORS, POLICY_LABELS, POLICY_ORDER, useApi } from "../api.js";
import { LeaderCard, Loading, PageHead, Status } from "../components.jsx";

export default function Policies({ go }) {
  const { data, error } = useApi("/policies", 30000);
  const { data: overview } = useApi("/overview");
  const [set, setSet] = useState("training");
  if (!data || !overview) return <Loading error={error} />;

  const scenarios = overview.scenarios.filter((s) => (set === "held_out") === s.held_out);
  const names = new Set(scenarios.map((s) => s.name));
  const rows = data.filter((r) => POLICY_ORDER.includes(r.policy) && names.has(r.scenario));
  const policies = POLICY_ORDER.filter((p) => rows.some((r) => r.policy === p));
  const ran = scenarios.filter((s) => rows.some((r) => r.scenario === s.name));

  // Totals only over failures that every listed policy ran, so the comparison is like for like.
  const shared = ran.filter((s) => policies.every((p) => rows.some((r) => r.policy === p && r.scenario === s.name)));
  const totals = policies.map((p) => {
    const mine = rows.filter((r) => r.policy === p && shared.some((s) => s.name === r.scenario));
    const trials = mine.reduce((n, r) => n + r.trials, 0);
    return {
      p, trials,
      recovered: mine.reduce((n, r) => n + r.recovered, 0),
      failed: mine.reduce((n, r) => n + r.failed_requests * r.trials, 0) / Math.max(trials, 1),
    };
  });

  return (
    <>
      <PageHead eyebrow="Policies" title="Rules vs. learning vs. LLM."
                right={<div className="seg" role="tablist">
                  <button className={set === "training" ? "on" : ""} onClick={() => setSet("training")}>Training failures</button>
                  <button className={set === "held_out" ? "on" : ""} onClick={() => setSet("held_out")}>Held-out failures</button>
                </div>}>
        {set === "training"
          ? "Each policy sees only live symptoms and chooses recovery actions — up to three per incident, every one safety-checked."
          : "Failures no policy was developed or trained on: the generalization test."}
      </PageHead>

      {rows.length === 0 ? <div className="card empty">No policy runs for this set yet — start one from Run.</div> : (
        <>
          <div className="grid grid-4">
            {totals.map((t) => (
              <section className="card" key={t.p}>
                <div className="kpi-label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <i style={{ width: 10, height: 10, background: POLICY_COLORS[t.p], display: "inline-block" }} />{POLICY_LABELS[t.p]}
                </div>
                <div className="kpi-value">{t.recovered}/{t.trials}</div>
                <div className="kpi-note">recovered · {Math.round(t.failed)} failed req per incident</div>
              </section>
            ))}
          </div>
          <p className="kpi-note" style={{ marginTop: 10 }}>
            Totals cover the {shared.length} failure{shared.length === 1 ? "" : "s"} every policy above ran, so they compare like for like.
          </p>

          <div className="grid grid-3">
            {ran.map((s) => <LeaderCard key={s.name} scenario={s} rows={rows} keyField="policy" onOpen={() => go("incidents")} />)}
          </div>

          <section className="card table-wrap">
            <h2>Table view</h2>
            <p className="sub">Median recovery and failed requests per incident, per policy and failure.</p>
            <table>
              <thead><tr><th>Failure</th>{policies.map((p) => <th key={p}>{POLICY_LABELS[p]}</th>)}</tr></thead>
              <tbody>
                {ran.map((s) => (
                  <tr key={s.name}>
                    <td className="mono" style={{ color: "var(--ink)" }}>{s.name}</td>
                    {policies.map((p) => {
                      const r = rows.find((x) => x.scenario === s.name && x.policy === p);
                      if (!r) return <td key={p}>–</td>;
                      return (
                        <td key={p}>
                          {r.recovered === r.trials ? <Status ok label={fmtS(r.median_s)} />
                            : r.recovered ? <Status warn label={`${r.recovered}/${r.trials} · ${fmtS(r.median_s)}`} />
                              : <Status label={`0/${r.trials}`} />}
                          <div className="kpi-note mono">{Math.round(r.failed_requests)} failed · {r.safety_blocked} blocked</div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}
