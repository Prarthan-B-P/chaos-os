import React from "react";
import { fmtS, useApi } from "../api.js";
import { Loading, PageHead } from "../components.jsx";

const ACTION_ORDER = ["none", "restart_redis", "restart_postgres", "restart_api", "cache_bypass", "warm_cache"];

export default function Matrix() {
  const { data, error } = useApi("/matrix", 30000);
  const { data: overview } = useApi("/overview");
  if (!data || !overview) return <Loading error={error} />;

  const scenarios = overview.scenarios.filter((s) => data.some((r) => r.scenario === s.name));
  const actions = ACTION_ORDER.filter((a) => data.some((r) => r.action === a));
  const cell = (s, a) => data.find((r) => r.scenario === s && r.action === a);
  const best = Object.fromEntries(scenarios.map((s) => {
    const full = data.filter((r) => r.scenario === s.name && r.trials > 0 && r.recovered === r.trials);
    full.sort((x, y) => x.median_s - y.median_s);
    return [s.name, full[0]?.action];
  }));

  return (
    <>
      <PageHead eyebrow="Recovery matrix" title="Every failure × every fix.">
        Each fixed recovery action tried against each training failure. ✓ cells recovered the service in every
        trial; the outlined cell is the fastest. ✕ cells never recovered — choosing them costs a full outage.
      </PageHead>
      {scenarios.length === 0 ? <div className="empty">No fixed-action trials yet.</div> : (
        <div className="table-wrap">
          <div className="matrix" style={{ gridTemplateColumns: `200px repeat(${actions.length}, minmax(130px, 1fr))`, minWidth: 200 + actions.length * 130 }}>
            <div className="matrix-head">Failure \ action</div>
            {actions.map((a) => <div key={a} className="matrix-head">{a}</div>)}
            {scenarios.map((s) => (
              <React.Fragment key={s.name}>
                <div className="matrix-row-head">
                  <div className="mono">{s.name}</div>
                  <div className="kpi-note" style={{ fontWeight: 400 }}>{s.description}</div>
                </div>
                {actions.map((a) => {
                  const c = cell(s.name, a);
                  if (!c) return <div key={a} className="matrix-cell"><span className="kpi-note">not run</span></div>;
                  const kind = best[s.name] === a ? "win" : c.recovered === c.trials ? "ok" : c.recovered ? "partial" : "fail";
                  return (
                    <div key={a} className={`matrix-cell ${kind}`}
                         title={`${c.recovered}/${c.trials} recovered · ${Math.round(c.failed_requests)} failed requests per trial`}>
                      <span className={`big ${c.recovered ? "" : "fail"}`}>
                        {c.recovered ? `✓ ${fmtS(c.median_s)}` : "✕"}
                      </span>
                      <span className="kpi-note mono">
                        {kind === "win" ? "best · " : ""}{c.recovered}/{c.trials} ok · {Math.round(c.failed_requests)} failed
                      </span>
                    </div>
                  );
                })}
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
