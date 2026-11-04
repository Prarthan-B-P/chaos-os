import React, { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, fmtPct, POLICY_COLORS, POLICY_LABELS, useApi } from "../api.js";
import { Card, Loading, PageHead } from "../components.jsx";

const axis = { stroke: "var(--axis)", tick: { fill: "var(--muted)", fontSize: 11.5, fontFamily: "var(--mono)" }, tickLine: false };

function CurveTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tooltip">
      <div className="tt-title">After {label} logged steps</div>
      <div className="tt-row">best action picked: <b style={{ color: "var(--ink)" }}>{fmtPct(p.accuracy)}</b></div>
      <div className="tt-row">mean regret: <b style={{ color: "var(--ink)" }}>{p.regret.toFixed(3)}</b></div>
    </div>
  );
}

export default function Learning() {
  const { data, error, reload } = useApi("/learning-curve");
  const [train, setTrain] = useState({ busy: false, error: null });
  const retrain = () => {
    setTrain({ busy: true, error: null });
    api("/train", { method: "POST" })
      .then(() => { setTrain({ busy: false, error: null }); reload(); })
      .catch((e) => setTrain({ busy: false, error: e.message }));
  };
  if (!data) return <Loading error={error} />;
  const last = data.curve.at(-1);

  return (
    <>
      <PageHead eyebrow="Learning" title="Does it learn?"
                right={<button className="btn primary" onClick={retrain} disabled={train.busy}>{train.busy ? "Training…" : "Retrain bandit"}</button>}>
        The bandit (LinUCB) is replayed over the logged training experiments in 30 random orders. After each amount of
        experience we check how often it picks the action that measurably worked best, from symptoms alone. Dashed lines
        are the fixed rule sets.
      </PageHead>
      {train.error && <p className="error">{train.error}</p>}
      {data.steps === 0 ? <Card><div className="empty">No training data yet.</div></Card> : (
        <div className="grid grid-3-1">
          <Card title="Best-action accuracy vs. experience" sub={`${data.steps} logged recovery steps, training failures only`}>
            <div className="legend">
              <span><i style={{ background: POLICY_COLORS.bandit }} />{POLICY_LABELS.bandit}</span>
              {Object.keys(data.baselines).map((k) => (
                <span key={k}><i style={{ background: POLICY_COLORS[k] }} />{POLICY_LABELS[k]} (fixed) · {fmtPct(data.baselines[k].accuracy)}</span>
              ))}
            </div>
            <div style={{ height: 340 }}>
              <ResponsiveContainer>
                <LineChart data={data.curve} margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid stroke="var(--grid)" vertical={false} />
                  <XAxis dataKey="steps_seen" {...axis} height={40}
                         label={{ value: "logged steps seen", fill: "var(--muted)", fontSize: 11.5, fontFamily: "var(--mono)", position: "insideBottom", offset: 0 }} />
                  <YAxis {...axis} axisLine={false} domain={[0, 1]} tickFormatter={fmtPct} width={46} />
                  <Tooltip content={<CurveTooltip />} />
                  {Object.entries(data.baselines).map(([k, b]) => (
                    <ReferenceLine key={k} y={b.accuracy} stroke={POLICY_COLORS[k]} strokeDasharray="5 4" strokeWidth={1.5} />
                  ))}
                  <Line type="monotone" dataKey="accuracy" stroke={POLICY_COLORS.bandit} strokeWidth={2}
                        dot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Best measured action" sub="What the data says works, per training failure">
            <table>
              <tbody>
                {Object.entries(data.best || {}).map(([s, a]) => (
                  <tr key={s}><td className="mono" style={{ color: "var(--ink)" }}>{s}</td><td className="mono">{a}</td></tr>
                ))}
              </tbody>
            </table>
            <div className="stat-num" style={{ marginTop: 22 }}>{fmtPct(last?.accuracy)}</div>
            <p className="kpi-note">final bandit accuracy · regret {last?.regret.toFixed(3)} (0 = always optimal)</p>
          </Card>
        </div>
      )}
    </>
  );
}
