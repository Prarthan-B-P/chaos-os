import { createContext, useCallback, useContext, useEffect, useState } from "react";

export async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.detail || `${res.status} ${res.statusText}`);
  if (body === null) throw new Error("unexpected response from the dashboard API");
  return body;
}

/** Fetch `path`, re-fetching every `intervalMs` while the tab is visible. */
export function useApi(path, intervalMs = 0) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api(path).then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message));
  }, [path]);

  useEffect(() => {
    load();
    if (!intervalMs) return undefined;
    const id = setInterval(() => { if (!document.hidden) load(); }, intervalMs);
    return () => clearInterval(id);
  }, [load, intervalMs]);

  return { data, error, reload: load };
}

/** One shared poll of the live lab for the whole app (it probes the system under test). */
export const LabContext = createContext({ data: null, reload: () => {} });
export const useLab = () => useContext(LabContext);

// Categorical slots, validated for the light surface (adjacent pairs, CVD-safe).
// Fixed per policy, never by rank, so a filter never repaints a series. Two slots
// sit below 3:1 contrast, so every chart also carries labels or a table view.
export const POLICY_COLORS = {
  rule_based: "#2a78d6",
  heuristic: "#1baf7a",
  bandit: "#eb6834",
  llm: "#6250d6",
  llm_agent: "#e87ba4",  // validated as slot 5 after the four above (below 3:1: always labelled)
};
export const POLICY_ORDER = ["rule_based", "heuristic", "bandit", "llm", "llm_agent"];

export const POLICY_LABELS = {
  rule_based: "Rule-based",
  heuristic: "Heuristic",
  bandit: "Bandit (learned)",
  llm: "LLM (gpt-4o-mini)",
  llm_agent: "LLM agent + tools",
  llm_sre: "LLM + SRE guidance",
  llm_agent_sre: "LLM agent + tools + guidance",
  adversarial: "Adversarial",
  fixed: "Fixed action",
};

export const POLICY_TAGS = { rule_based: "runbook", heuristic: "expert", bandit: "learned", llm: "gen ai", llm_agent: "agentic" };

// Locally the dashboard is served on :8090 and the other tools on their own ports.
// Deployed, everything sits behind the Caddy proxy: Grafana under /grafana on the
// same origin, and Jenkins is private (not linked).
const proxied = window.location.port !== "8090";
export const LINKS = {
  grafana: proxied
    ? "/grafana/d/chaos-os-service-health"
    : `http://${window.location.hostname}:3000/d/chaos-os-service-health`,
  jenkins: proxied ? null : `http://${window.location.hostname}:8081/job/chaos-os-ci/`,
  github: "https://github.com/Prarthan-B-P/chaos-os",
};

export const fmtS = (x) => (x == null ? "–" : `${x.toFixed(1)}s`);
export const fmtPct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString([], {
  month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
}) : "–");
export const isToday = (iso) => iso && new Date(iso).toDateString() === new Date().toDateString();

/** LLM text is shown as plain prose: drop markdown emphasis, headings and code ticks. */
export const plain = (text) => (text || "")
  .replace(/\*\*(.*?)\*\*/g, "$1").replace(/__(.*?)__/g, "$1")
  .replace(/^#{1,6}\s*/gm, "").replace(/`/g, "");
