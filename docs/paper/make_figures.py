"""Data figures for the CHAOS OS paper and study guide, straight from the lab's APIs.

    python docs/paper/make_figures.py [--campaign oncall-campaign.json] [--drill-incident ID]

Reads the dashboard API (experiments, policies, learning curve, on-call records)
and Prometheus (SLI time series). Writes PDF (paper) and PNG (study guide) files
into docs/paper/figures/, plus results.json with every number the text quotes.
"""
import argparse
import json
import statistics
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

OUT = Path(__file__).parent / "figures"
DASH = "http://localhost:8090"
PROM = "http://localhost:9090"

TRAINING = ["redis_down", "redis_latency", "postgres_latency", "postgres_down", "api_crash"]
HELD_OUT = ["redis_partition", "redis_down_slow_db"]
ACTIONS = ["restart_redis", "restart_postgres", "restart_api", "cache_bypass", "warm_cache"]
POLICIES = ["rule_based", "heuristic", "bandit", "llm"]
# The dashboard's validated categorical slots (see dashboard/web/src/api.js).
COLORS = {"rule_based": "#2a78d6", "heuristic": "#1baf7a", "bandit": "#eb6834", "llm": "#6250d6",
          "llm_agent": "#e87ba4"}
MARKERS = {"rule_based": "s", "heuristic": "D", "bandit": "o", "llm": "^"}
LABELS = {"rule_based": "Rule-based runbook", "heuristic": "Expert heuristic",
          "bandit": "LinUCB bandit", "llm": "LLM (gpt-4o-mini)",
          "llm_sre": "LLM + SRE guidance", "llm_agent": "LLM agent + tools",
          "llm_agent_sre": "Agent + tools + guidance"}
INK, MUTED, GRID = "#0e0e0f", "#6b6965", "#e6e3de"
ORIGINAL_MAX_ID = 118   # Phase 5/6 policy comparison (before on-call mode existed)
ABLATION_MIN_ID = 121   # the 2x2 LLM ablation batch

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 6.8, "axes.edgecolor": MUTED,
    "axes.linewidth": 0.6, "xtick.color": MUTED, "ytick.color": INK, "axes.labelcolor": INK,
    "xtick.major.width": 0.6, "ytick.major.width": 0, "axes.spines.top": False,
    "axes.spines.right": False, "savefig.dpi": 220, "pdf.fonttype": 42,
})


def get(url: str):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def summarize(trials: list[dict], key: str) -> dict:
    """(scenario, key) -> n, recovered, median/min/max recovery, mean failed requests."""
    groups = defaultdict(list)
    for t in trials:
        if t["valid"]:
            groups[(t["scenario"], t[key] or "fixed")].append(t)
    out = {}
    for k, ts in groups.items():
        times = sorted(t["recovery_time_s"] for t in ts if t["recovered"])
        out[k] = {"n": len(ts), "recovered": len(times),
                  "median_s": statistics.median(times) if times else None,
                  "min_s": times[0] if times else None, "max_s": times[-1] if times else None,
                  "failed": statistics.mean(t["incident_failures"] for t in ts),
                  "actions": sorted({t["actions"] or t["action"] for t in ts})}
    return out


# ---------------------------------------------------------------- figures

def fig_matrix(trials: list[dict], results: dict) -> None:
    # The original matrix (two trials per cell); later gate runs are fixed-action trials too.
    fixed = [t for t in trials if t["id"] <= ORIGINAL_MAX_ID and t["policy"] in (None, "fixed")
             and t["scenario"] in TRAINING]
    s = summarize(fixed, "action")
    results["matrix"] = {f"{a}|{b}": v for (a, b), v in s.items()}
    fig, ax = plt.subplots(figsize=(3.45, 2.15))
    cmap = matplotlib.colormaps["Blues"]
    for i, scen in enumerate(TRAINING):
        for j, act in enumerate(ACTIONS):
            cell = s.get((scen, act))
            if not cell:
                continue
            if cell["recovered"] == 0:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor="#f3f1ed",
                                           edgecolor="white", hatch="////", linewidth=1.5))
                ax.text(j, i, "never", ha="center", va="center", color=MUTED, fontsize=6.5)
                continue
            shade = min(1.0, 0.25 + cell["median_s"] / 25)
            ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor=cmap(shade),
                                       edgecolor="white", linewidth=1.5))
            ax.text(j, i - 0.12, f"{cell['median_s']:.1f} s", ha="center", va="center",
                    color="white" if shade > 0.55 else INK, fontsize=7, fontweight="bold")
            ax.text(j, i + 0.22, f"{cell['failed']:.0f} failed", ha="center", va="center",
                    color="white" if shade > 0.55 else MUTED, fontsize=5.6)
    ax.set_xlim(-0.5, len(ACTIONS) - 0.5)
    ax.set_ylim(len(TRAINING) - 0.5, -0.5)
    ax.set_xticks(range(len(ACTIONS)), [a.replace("_", "\n") for a in ACTIONS])
    ax.set_yticks(range(len(TRAINING)), TRAINING)
    ax.tick_params(length=0)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_title("Median recovery with each fixed action (2 trials each)", loc="left", color=INK)
    save(fig, "fig_matrix")


def dot_plot(ax, rows: list[str], series: list[str], data: dict, style, title: str,
             fail_x: float = 150) -> None:
    """One row per scenario, one marker per series; failures drawn at the right edge."""
    k = len(series)
    for i, scen in enumerate(rows):
        for j, name in enumerate(series):
            cell = data.get((scen, name))
            if not cell:
                continue
            y = i + (j - (k - 1) / 2) * 0.17
            color, marker, filled = style(name)
            if cell["recovered"] == 0:
                ax.scatter([fail_x], [y], marker="x", s=22, color=color, linewidths=1.3, zorder=3)
                continue
            if cell["max_s"] > cell["min_s"]:
                ax.plot([cell["min_s"], cell["max_s"]], [y, y], color=color, linewidth=1, alpha=0.8)
            ax.scatter([cell["median_s"]], [y], marker=marker, s=26, zorder=3,
                       facecolor=color if filled else "white", edgecolor=color, linewidths=1.1)
            if cell["recovered"] < cell["n"]:
                ax.text(cell["max_s"] * 1.15, y, f"{cell['recovered']}/{cell['n']}", va="center",
                        fontsize=5.6, color=MUTED)
    ax.set_xscale("log")
    ax.set_xlim(0.5, 260)
    ax.axvspan(100, 260, color="#f3f1ed", zorder=0)
    ax.set_xticks([1, 3, 10, 30, 90, fail_x], ["1 s", "3 s", "10 s", "30 s", "90 s", "not\nrecovered"])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_yticks(range(len(rows)), rows)
    ax.set_ylim(len(rows) - 0.4, -0.9)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.set_title(title, loc="left", color=INK)


def fig_policies(trials: list[dict], results: dict) -> None:
    orig = [t for t in trials if t["id"] <= ORIGINAL_MAX_ID and t["policy"] in POLICIES]
    s = summarize(orig, "policy")
    results["policies"] = {f"{a}|{b}": v for (a, b), v in s.items()}
    fig, ax = plt.subplots(figsize=(3.45, 3.1))
    dot_plot(ax, TRAINING + HELD_OUT, POLICIES, s,
             lambda n: (COLORS[n], MARKERS[n], True),
             "Median recovery (range) per policy; held-out failures last")
    ax.axhline(len(TRAINING) - 0.5, color=MUTED, linewidth=0.6, linestyle=(0, (3, 2)))
    ax.set_xlabel("Recovery time, fault injection to sustained healthy traffic (log scale)")
    handles = [Line2D([], [], marker=MARKERS[p], color=COLORS[p], linestyle="", markersize=5,
                      label=LABELS[p]) for p in POLICIES]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.45, -0.2), ncol=2, frameon=False)
    save(fig, "fig_policies")


def fig_learning(curve: dict, results: dict) -> None:
    results["learning_curve"] = curve
    pts = curve["curve"]
    fig, ax = plt.subplots(figsize=(3.45, 1.9))
    ax.plot([p["steps_seen"] for p in pts], [p["accuracy"] for p in pts], color=COLORS["bandit"],
            linewidth=2, marker="o", markersize=3.5, label=LABELS["bandit"])
    for name, b in curve["baselines"].items():
        ax.axhline(b["accuracy"], color=COLORS.get(name, MUTED), linewidth=1, linestyle=(0, (4, 2)))
        ax.text(pts[-1]["steps_seen"], b["accuracy"] + 0.025, f"{LABELS.get(name, name)} "
                f"{b['accuracy']:.0%}", ha="right", va="bottom", fontsize=6.5, color=MUTED)
    last = pts[-1]
    ax.annotate(f"{last['accuracy']:.0%}", (last["steps_seen"], last["accuracy"]), xytext=(4, -10),
                textcoords="offset points", fontsize=7, color=INK)
    ax.set_ylim(0, 1.08)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel(f"Logged training steps seen (replayed in {curve.get('permutations', 30)} random orders)")
    ax.set_ylabel("Best-action accuracy")
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_title("Bandit accuracy vs. experience, against fixed rules", loc="left", color=INK)
    save(fig, "fig_learning")


def fig_ablation(trials: list[dict], results: dict) -> None:
    variants = ["llm", "llm_sre", "llm_agent", "llm_agent_sre"]
    batch = [t for t in trials if t["id"] >= ABLATION_MIN_ID and t["policy"] in variants]
    s = summarize(batch, "policy")
    results["ablation"] = {f"{a}|{b}": v for (a, b), v in s.items()}
    results["ablation_trials"] = len(batch)
    tools = {"llm": False, "llm_sre": False, "llm_agent": True, "llm_agent_sre": True}
    style = lambda n: ("#eb6834" if tools[n] else "#2a78d6", "o" if tools[n] else "s", n.endswith("_sre"))
    fig, ax = plt.subplots(figsize=(3.45, 3.0))
    dot_plot(ax, TRAINING + HELD_OUT, variants, s, style,
             "LLM ablation: tools x generic SRE guidance (2 trials each)")
    ax.axhline(len(TRAINING) - 0.5, color=MUTED, linewidth=0.6, linestyle=(0, (3, 2)))
    ax.set_xlabel("Recovery time (log scale)")
    handles = [Line2D([], [], marker=style(v)[1], linestyle="", markersize=5,
                      markerfacecolor=style(v)[0] if style(v)[2] else "white",
                      markeredgecolor=style(v)[0], label=LABELS[v]) for v in variants]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.45, -0.2), ncol=2, frameon=False)
    save(fig, "fig_ablation")


def prom_range(query: str, start: datetime, end: datetime, step: float = 2.0) -> list[tuple]:
    q = urllib.parse.urlencode({"query": query, "start": start.timestamp(), "end": end.timestamp(),
                                "step": step})
    data = get(f"{PROM}/api/v1/query_range?{q}")["data"]["result"]
    return [(float(t), float(v)) for t, v in data[0]["values"]] if data else []


def fig_oncall_timeline(oncall: dict, incident_id: int, results: dict) -> None:
    inc = get(f"{DASH}/api/oncall/incidents/{incident_id}")
    match = next(m for m in oncall["score"]["matches"] if m["incident_id"] == incident_id)
    fault = datetime.fromisoformat(match["event"]["at"])
    t0 = fault - timedelta(seconds=40)
    t1 = fault + timedelta(seconds=150)
    burn1m = prom_range("slo:bad_ratio:rate1m / 0.01", t0, t1)
    burn20 = prom_range("slo:bad_ratio:rate20s / 0.01", t0, t1)
    rel = lambda ts: ts - fault.timestamp()
    fig, ax = plt.subplots(figsize=(7.0, 2.2))
    ax.plot([rel(t) for t, _ in burn1m], [v for _, v in burn1m], color=INK, linewidth=1.8,
            label="burn rate, 1 min window")
    ax.plot([rel(t) for t, _ in burn20], [v for _, v in burn20], color="#2a78d6", linewidth=1.3,
            label="burn rate, 20 s window")
    ax.axhline(14.4, color="#d03b3b", linewidth=1, linestyle=(0, (4, 2)))
    ax.text(108, 15.5, "page threshold 14.4x", ha="right", va="bottom", fontsize=6.5, color="#a82424")
    marks = [(0, "fault injected\n(agent not told)"),
             (match["detect_s"], "SLO alert fires"),
             (match["engage_s"], "agent paged,\nprobe confirms")]
    for e in inc["timeline"]:
        if e["kind"] == "action":
            marks.append((match["engage_s"] + e["t"], f"runs {e['action']}"))
    if match["recover_s"] is not None:
        marks.append((match["recover_s"], "healthy again"))
    top = max([v for _, v in burn20] + [20])
    ymax = top * 1.32
    marks.sort()
    key = []
    for i, (x, label) in enumerate(marks):
        ax.plot([x, x], [0, top * 1.06], color=MUTED, linewidth=0.7)
        # Numbered markers on the lines (staggered when close), explained in a key below.
        level = 1.1 if i % 2 == 0 else 1.22
        ax.text(x, top * level, str(i + 1), ha="center", va="center", fontsize=6, color="white",
                fontweight="bold", bbox={"boxstyle": "circle,pad=0.25", "facecolor": INK, "linewidth": 0})
        key.append(f"{i + 1}  {label.replace(chr(10), ' ')} (+{x:.1f} s)")
    half = (len(key) + 1) // 2
    ax.text(0, -0.36, "     ".join(key[:half]) + "\n" + "     ".join(key[half:]),
            transform=ax.transAxes, fontsize=6.3, color=INK, va="top", linespacing=1.6)
    ax.set_ylim(0, ymax)
    ax.set_xlim(-15, 110)
    ax.set_xlabel("Seconds since the fault was injected")
    ax.set_ylabel("Error-budget burn rate")
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.legend(loc="center right", frameon=False)
    ax.set_title(f"Unannounced {match['event']['scenario']}: page, confirmation and fix "
                 f"(incident #{incident_id})", loc="left", color=INK, pad=16)
    results["timeline_incident"] = {"incident": incident_id, "match": match, "timeline": inc["timeline"]}
    save(fig, "fig_oncall_timeline")


def fig_campaign(campaign: list[dict], results: dict) -> None:
    by = defaultdict(list)
    for r in campaign:
        by[r["scenario"]].append(r)
    rows = [s for s in TRAINING + HELD_OUT if s in by]
    summary = {}
    fig, ax = plt.subplots(figsize=(3.45, 2.5))
    ramp = ["#9ec5f4", "#3987e5", "#1c5cab"]  # ordinal blue steps: detect, engage, recover
    for i, scen in enumerate(rows):
        rs = by[scen]
        med = lambda k: statistics.median([r[k] for r in rs if r[k] is not None]) if any(
            r[k] is not None for r in rs) else None
        d, e, h = med("detect_s"), med("engage_s"), med("recover_s")
        healed = sum(r["status"] == "resolved" for r in rs)
        summary[scen] = {"n": len(rs), "healed": healed, "detect_s": d, "engage_s": e, "recover_s": h,
                         "actions": sorted({r["actions"] or "-" for r in rs})}
        left = 0
        for value, color in zip((d, e, h), ramp):
            if value is None:
                continue
            ax.barh(i, value - left, left=left, color=color, height=0.55, edgecolor="white", linewidth=1)
            left = value
        label = f"{healed}/{len(rs)} healed" + (f", {h:.0f} s" if h is not None else "")
        ax.text(left + 2, i, label, va="center", fontsize=6.3, color=INK if healed else "#a82424")
    ax.set_yticks(range(len(rows)), rows)
    ax.set_ylim(len(rows) - 0.5, -0.6)
    ax.set_xlabel("Seconds since the unannounced fault (medians)")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in ramp]
    ax.legend(handles, ["until the alert fires", "until the agent engages", "until traffic is healthy"],
              loc="upper center", bbox_to_anchor=(0.42, -0.22), ncol=3, frameon=False)
    ax.set_title("On-call mode: unannounced faults, end to end", loc="left", color=INK)
    results["campaign"] = summary
    results["campaign_rows"] = campaign
    save(fig, "fig_campaign")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign")
    parser.add_argument("--drill-incident", type=int)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    trials = get(f"{DASH}/api/trials?limit=5000")
    results["trial_count"] = len(trials)
    fig_matrix(trials, results)
    fig_policies(trials, results)
    fig_learning(get(f"{DASH}/api/learning-curve"), results)
    fig_ablation(trials, results)
    oncall = get(f"{DASH}/api/oncall")
    results["oncall_score"] = {k: v for k, v in oncall["score"].items() if k != "matches"}
    if args.drill_incident:
        fig_oncall_timeline(oncall, args.drill_incident, results)
    if args.campaign:
        fig_campaign(json.load(open(args.campaign)), results)
    (OUT / "results.json").write_text(json.dumps(results, indent=2, default=str))
    print("wrote results.json")


if __name__ == "__main__":
    main()
