import React from "react";
import { fmtS, POLICY_COLORS, POLICY_LABELS, POLICY_TAGS } from "./api.js";

const PATHS = {
  arrow: "M5 12h14M13 6l6 6-6 6",
  external: "M7 17L17 7M9 7h8v8",
  mic: "M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3zM5 11a7 7 0 0014 0M12 18v3",
  x: "M6 6l12 12M18 6L6 18",
  refresh: "M20 11a8 8 0 10-2.3 5.7M20 4v7h-7",
  logo: "M4 13.5l4.5-6 4 8.5 3-5 4.5 4",
};

export function Icon({ name, ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d={PATHS[name]} />
    </svg>
  );
}

export function Card({ title, sub, children, className = "", right, style }) {
  return (
    <section className={`card ${className}`} style={style}>
      {(title || right) && (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
          <div>
            {title && <h2>{title}</h2>}
            {sub && <p className="sub">{sub}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

/** Status is never color alone: dot + glyph + label. */
export function Status({ ok, label, warn = false, pulse = false }) {
  const kind = warn ? "warn" : ok ? "good" : "bad";
  return (
    <span className={`status ${kind} ${pulse && ok ? "pulse" : ""}`}>
      <span className="dot" aria-hidden="true" />
      {warn ? "!" : ok ? "✓" : "✕"} {label}
    </span>
  );
}

export function PageHead({ eyebrow, title, children, right }) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow bracket">{eyebrow}</div>}
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {right}
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="legend" role="list">
      {items.map(([key, color]) => (
        <span key={key} role="listitem"><i style={{ background: color }} />{POLICY_LABELS[key] || key}</span>
      ))}
    </div>
  );
}

export function ChartTooltip({ active, payload, label, unit = "", labelFmt }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="tt-title">{labelFmt ? labelFmt(label) : label}</div>
      {payload.map((p) => (
        <div className="tt-row" key={p.dataKey}>
          <i style={{ width: 8, height: 8, background: p.color, display: "inline-block" }} />
          {POLICY_LABELS[p.dataKey] || p.name}: <b style={{ color: "var(--ink)" }}>
            {p.value == null ? "no data" : `${typeof p.value === "number" ? p.value.toFixed(p.value < 10 ? 1 : 0) : p.value}${unit}`}
          </b>
        </div>
      ))}
    </div>
  );
}

export function Loading({ error }) {
  return <div className={error ? "error" : "empty"}>{error || "Loading…"}</div>;
}

/**
 * Ranked recovery results for one failure: responders ordered by recovery rate,
 * then median recovery time. Bars show the median (shorter is better); whiskers
 * show the min-max range across repeated trials.
 */
export function LeaderCard({ scenario, rows, keyField, onOpen }) {
  const entries = rows
    .filter((r) => r.scenario === scenario.name)
    .map((r) => ({ ...r, key: r[keyField], rate: r.trials ? r.recovered / r.trials : 0 }))
    .sort((a, b) => (b.rate - a.rate) || ((a.median_s ?? 1e9) - (b.median_s ?? 1e9))
      || (a.failed_requests - b.failed_requests));
  const maxT = Math.max(...entries.map((e) => e.max_s ?? 0), 1);
  const pct = (x) => `${Math.min(100, (x / maxT) * 100)}%`;

  return (
    <article className="card lb-card">
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <span className="tag">{scenario.name}</span>
        {scenario.held_out && <span className="tag held">held out</span>}
      </div>
      <h3 style={{ marginTop: 10 }}>{scenario.description}</h3>
      <p>Median recovery, range across trials. Shorter is better.</p>
      {entries.length === 0 ? <div className="empty">Not run yet</div> : (
        <ol className="lb-list">
          {entries.map((e, i) => {
            const color = keyField === "policy" ? POLICY_COLORS[e.key] : i === 0 && e.recovered ? "var(--accent)" : "#55534f";
            const label = keyField === "policy" ? POLICY_LABELS[e.key] || e.key : e.key;
            return (
              <li key={e.key} title={`${label}: ${e.recovered}/${e.trials} recovered · ${Math.round(e.failed_requests)} failed requests per incident`}>
                <span className={`rank r${i + 1}`}>{i + 1}</span>
                <div>
                  <div className="lb-top">
                    <span>{label}</span>
                    {keyField === "policy" && POLICY_TAGS[e.key] && <span className="tag">{POLICY_TAGS[e.key]}</span>}
                    <span className="score">
                      {e.recovered
                        ? <>{fmtS(e.median_s)}{e.trials > 1 && <span> {e.min_s.toFixed(1)}–{e.max_s.toFixed(1)}</span>}</>
                        : <span>✕ {e.recovered}/{e.trials}</span>}
                    </span>
                  </div>
                  <div className="bar-track">
                    {e.recovered > 0 && <div className="bar-fill" style={{ width: pct(e.median_s), background: color }} />}
                    {e.recovered > 1 && e.max_s > e.min_s && (
                      <span className="whisker" style={{ left: pct(e.min_s), width: `calc(${pct(e.max_s)} - ${pct(e.min_s)})` }} />
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {onOpen && <div className="foot"><button className="link" onClick={onOpen}>View incidents →</button></div>}
    </article>
  );
}
