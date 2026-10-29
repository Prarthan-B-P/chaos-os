import React, { useEffect, useState } from "react";
import { LabContext, LINKS, useApi, useLab } from "./api.js";
import { Icon } from "./components.jsx";
import Overview from "./pages/Overview.jsx";
import Matrix from "./pages/Matrix.jsx";
import Policies from "./pages/Policies.jsx";
import Learning from "./pages/Learning.jsx";
import Incidents from "./pages/Incidents.jsx";
import Run from "./pages/Run.jsx";
import Safety from "./pages/Safety.jsx";

const PAGES = [
  ["overview", "Overview", Overview],
  ["matrix", "Matrix", Matrix],
  ["policies", "Policies", Policies],
  ["learning", "Learning", Learning],
  ["incidents", "Incidents", Incidents],
  ["run", "Run", Run],
  ["safety", "Safety", Safety],
];

function currentPage() {
  const hash = window.location.hash.replace("#/", "").split("/")[0];
  return PAGES.some(([id]) => id === hash) ? hash : "overview";
}

function LiveStrip({ go }) {
  const { data } = useLab();
  const up = data?.services.filter((s) => s.state === "running").length ?? 0;
  const total = data?.services.length ?? 0;
  const faults = (data?.proxies ?? []).filter((p) => !p.enabled || p.toxics.length).map((p) => p.proxy);
  const fault = faults.length > 0 || up < total;
  return (
    <div className="topline" role="status">
      <div className="container">
        <span className="live"><i className={fault ? "fault" : ""} aria-hidden="true" />
          {data ? `LIVE · chaosos lab ${fault ? "· fault active" : "· healthy"} · ${up}/${total} services up` : "Connecting to the lab…"}
          {faults.length > 0 && ` · ${faults.join(", ")} degraded`}
        </span>
        <button onClick={() => go("run")}>Run an experiment →</button>
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState(currentPage);
  const lab = useApi("/lab", 5000);

  useEffect(() => {
    const onHash = () => setPage(currentPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (id) => { window.location.hash = `#/${id}`; };

  // Ctrl/Cmd+K: jump to "Ask the lab".
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        go("overview");
        setTimeout(() => document.getElementById("ask-input")?.focus(), 50);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const Page = PAGES.find(([id]) => id === page)[2];

  return (
    <LabContext.Provider value={lab}>
      <LiveStrip go={go} />
      <header className="nav">
        <div className="container">
          <button className="logo" onClick={() => go("overview")} aria-label="CHAOS OS home">
            <span className="logo-mark"><Icon name="logo" /></span>
            <span className="logo-text">chaos os <span>lab</span></span>
          </button>
          <nav className="navlinks" aria-label="Sections">
            {PAGES.map(([id, label]) => (
              <button key={id} className={page === id ? "active" : ""} onClick={() => go(id)}
                      aria-current={page === id ? "page" : undefined}>{label}</button>
            ))}
          </nav>
          <span className="kbd" title="Ask the lab">Ctrl K</span>
          <button className="btn primary sm nav-cta" onClick={() => go("run")}>Run experiment <Icon name="arrow" /></button>
        </div>
      </header>
      <main className={page === "overview" ? "" : "container main"}>
        <Page go={go} />
      </main>
      <footer className="footer">
        <div className="container">
          <span>CHAOS OS — break it. learn from it. build infrastructure that survives it.</span>
          <a href={LINKS.grafana} target="_blank" rel="noreferrer">Grafana ↗</a>
          <a href={LINKS.jenkins} target="_blank" rel="noreferrer">Jenkins ↗</a>
          <a href={LINKS.github} target="_blank" rel="noreferrer">GitHub ↗</a>
        </div>
      </footer>
    </LabContext.Provider>
  );
}
