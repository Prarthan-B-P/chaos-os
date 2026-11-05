"""LaTeX tables and number macros for the paper, from figures/results.json (+ facts.json).

    python docs/paper/make_tables.py      -> docs/paper/generated/*.tex
"""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).parent
R = json.loads((HERE / "figures" / "results.json").read_text())
FACTS = HERE.parent / "study-guide" / "facts.json"
F = json.loads(FACTS.read_text()) if FACTS.exists() else {}
OUT = HERE / "generated"
OUT.mkdir(exist_ok=True)

TRAINING = ["redis_down", "redis_latency", "postgres_latency", "postgres_down", "api_crash"]
HELD_OUT = ["redis_partition", "redis_down_slow_db"]
ACTIONS = ["restart_redis", "restart_postgres", "restart_api", "cache_bypass", "warm_cache"]


def tt(name: str) -> str:
    return r"\texttt{" + name.replace("_", r"\_") + "}"


def cell(c: dict | None, bold: bool = False) -> str:
    if not c:
        return "--"
    if not c["recovered"]:
        return rf"$\times$ 0/{c['n']}"
    text = f"{c['recovered']}/{c['n']}, {c['median_s']:.1f}"
    if f"{c['max_s']:.1f}" != f"{c['min_s']:.1f}":
        text += rf"\,{{\scriptsize({c['min_s']:.1f}--{c['max_s']:.1f})}}"
    return rf"\textbf{{{text}}}" if bold else text


def best_key(cells: dict) -> str | None:
    """The fastest full recovery in a row (bolded)."""
    full = {k: c for k, c in cells.items() if c and c["recovered"] == c["n"]}
    return min(full, key=lambda k: full[k]["median_s"]) if full else None


def write(name: str, text: str) -> None:
    (OUT / name).write_text(text, encoding="utf-8")
    print("wrote", name)


def table_rows(rows: list[str], cols: list[str], data: dict, label=lambda s: s) -> str:
    lines = []
    for i, scen in enumerate(rows):
        if i == len(TRAINING) and len(rows) > len(TRAINING):
            lines.append(r"\midrule")
        cells = {c: data.get(f"{scen}|{c}") for c in cols}
        best = best_key(cells)
        lines.append(tt(label(scen)) + " & " + " & ".join(cell(cells[c], c == best) for c in cols) + r" \\")
    return "\n".join(lines)


def totals(cols: list[str], data: dict, rows: list[str]) -> str:
    out = []
    for c in cols:
        rec = sum(data.get(f"{s}|{c}", {}).get("recovered", 0) for s in rows)
        n = sum(data.get(f"{s}|{c}", {}).get("n", 0) for s in rows)
        out.append(f"{rec}/{n}")
    return r"\textit{recovered} & " + " & ".join(out) + r" \\"


# Fixed-action matrix ----------------------------------------------------------
M = R["matrix"]
write("tab_matrix.tex", "\n".join([
    r"\begin{tabular}{@{}l" + "c" * len(ACTIONS) + r"@{}}", r"\toprule",
    "Failure & " + " & ".join(r"\shortstack{" + a.replace("_", r"\_\\") + "}" for a in ACTIONS) + r" \\",
    r"\midrule",
    "\n".join(tt(s) + " & " + " & ".join(
        (rf"\textbf{{{M[f'{s}|{a}']['median_s']:.1f}}}" if M.get(f"{s}|{a}", {}).get("recovered") else r"$\times$")
        for a in ACTIONS) + r" \\" for s in TRAINING),
    r"\bottomrule", r"\end{tabular}"]))

# Policies ---------------------------------------------------------------------
P = R["policies"]
pol = ["rule_based", "heuristic", "bandit", "llm"]
write("tab_policies.tex", "\n".join([
    r"\begin{tabular}{@{}lcccc@{}}", r"\toprule",
    r"Failure & Runbook & Heuristic & Bandit & LLM \\", r"\midrule",
    table_rows(TRAINING + HELD_OUT, pol, P), r"\midrule", totals(pol, P, TRAINING + HELD_OUT),
    r"\bottomrule", r"\end{tabular}"]))

# Ablation ---------------------------------------------------------------------
A = R["ablation"]
var = ["llm", "llm_sre", "llm_agent", "llm_agent_sre"]
write("tab_ablation.tex", "\n".join([
    r"\begin{tabular}{@{}lcccc@{}}", r"\toprule",
    r" & \multicolumn{2}{c}{No tools} & \multicolumn{2}{c}{Tools (agent)} \\",
    r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}",
    r"Failure & no guid. & guidance & no guid. & guidance \\", r"\midrule",
    table_rows(TRAINING + HELD_OUT, var, A), r"\midrule", totals(var, A, TRAINING + HELD_OUT),
    r"\bottomrule", r"\end{tabular}"]))

# On-call campaign -------------------------------------------------------------
C = R.get("campaign", {})
fmt = lambda x: "--" if x is None else f"{x:.1f}"
rows = []
for i, s in enumerate([s for s in TRAINING + HELD_OUT if s in C]):
    if i == len(TRAINING):
        rows.append(r"\midrule")
    c = C[s]
    acts = "; ".join(a.replace("_", r"\_") for a in c["actions"])
    rows.append(f"{tt(s)} & {c['healed']}/{c['n']} & {fmt(c['detect_s'])} & {fmt(c['engage_s'])} & "
                f"{fmt(c['recover_s'])} & {{\\scriptsize {acts}}} \\\\")
write("tab_campaign.tex", "\n".join([
    r"\begin{tabular}{@{}lccccp{2.55cm}@{}}", r"\toprule",
    r"Failure & Healed & Alert & Engage & Healthy & Actions \\", r"\midrule", *rows,
    r"\bottomrule", r"\end{tabular}"]))

# CI stage durations (facts.json, read from the Jenkins build log) ---------------
ci = F.get("ci", {})
if ci.get("stages"):
    demo = {s["name"]: s for s in ci.get("demo", {}).get("stages", [])}
    lines = []
    for s in ci["stages"]:
        d = demo.get(s["name"])
        dtext = "--" if not d else (f"{d['seconds']}" + (r" $\times$" if d.get("failed") else ""))
        lines.append(f"{s['name']} & {s['seconds']} & {dtext} \\\\")
    write("tab_ci.tex", "\n".join([
        r"\begin{tabular}{@{}lrr@{}}", r"\toprule",
        r"Stage & \texttt{main} (s) & demo bug (s) \\", r"\midrule", *lines, r"\midrule",
        rf"Total & {ci['duration_s']} & {ci.get('demo', {}).get('duration_s', '--')} \\",
        r"\bottomrule", r"\end{tabular}"]))

# Macros -----------------------------------------------------------------------
lc = R["learning_curve"]
rows_c = R.get("campaign_rows", [])
med = lambda xs: statistics.median(xs) if xs else None
macros = {
    "nTrials": R["trial_count"],
    "nAblation": R.get("ablation_trials", 0),
    "lcSteps": lc["steps"],
    "lcBandit": f"{round(lc['curve'][-1]['accuracy'] * 100)}\\%",
    "lcHeuristic": f"{round(lc['baselines']['heuristic']['accuracy'] * 100)}\\%",
    "lcRunbook": f"{round(lc['baselines']['rule_based']['accuracy'] * 100)}\\%",
    # On-call figures come from the controlled campaign only (steady state before every fault).
    "ocFaults": len(rows_c),
    "ocHealed": sum(r["status"] == "resolved" for r in rows_c),
    "ocEscalated": sum(r["status"] == "escalated" for r in rows_c),
    "ocMedDetect": fmt(med([r["detect_s"] for r in rows_c if r["detect_s"] is not None])),
    "ocMedEngage": fmt(med([r["engage_s"] for r in rows_c if r["engage_s"] is not None])),
    "ocMedRecover": fmt(med([r["recover_s"] for r in rows_c if r["recover_s"] is not None])),
    "ocApprovals": sum(r.get("approvals", 0) for r in rows_c),
}
write("macros.tex", "\n".join(rf"\newcommand{{\{k}}}{{{v}}}" for k, v in macros.items()) + "\n")
