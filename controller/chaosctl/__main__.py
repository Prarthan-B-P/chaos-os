"""CLI.

  python -m chaosctl list
  python -m chaosctl run --scenario redis_down --action restart_redis,cache_bypass --reps 3
  python -m chaosctl report
  python -m chaosctl gate --scenario redis_down --action restart_redis --max-recovery 30
"""
import argparse
import asyncio
import sys

from . import store
from .actions import ACTIONS
from .experiment import TrialResult, run_trial
from .scenarios import SCENARIOS


def _pick(value: str, options: dict, kind: str) -> list:
    names = list(options) if value == "all" else value.split(",")
    unknown = [n for n in names if n not in options]
    if unknown:
        sys.exit(f"unknown {kind}: {', '.join(unknown)} (choose from {', '.join(options)})")
    return [options[n] for n in names]


def _describe(t: TrialResult) -> str:
    if not t.valid:
        return f"INVALID baseline (success={t.baseline_success}, p95={t.baseline_p95_ms} ms)"
    if not t.impacted:
        return "fault had no measurable impact"
    outcome = (f"recovered in {t.recovery_time_s:.1f}s" if t.recovered
               else "did NOT recover within the timeout")
    action = ("" if t.action == "none" or t.action_ok is None
              else f", action {'ok' if t.action_ok else 'FAILED'} in {t.action_duration_s:.1f}s")
    return (f"{outcome} (detected after {t.detected_after_s:.1f}s{action}); "
            f"availability {t.incident_availability:.1%}, "
            f"{t.incident_failures}/{t.incident_requests} requests failed")


def _run(scenarios, actions, reps: int) -> list[TrialResult]:
    results = []
    for scenario in scenarios:
        for action in actions:
            for rep in range(1, reps + 1):
                print(f"[{scenario.name} / {action.name} #{rep}] running...", flush=True)
                trial = asyncio.run(run_trial(scenario, action))
                store.save(trial)
                print(f"[{scenario.name} / {action.name} #{rep}] {_describe(trial)}", flush=True)
                results.append(trial)
    return results


def _fmt(x: float | None, spec: str, unit: str = "") -> str:
    return "-" if x is None else format(x, spec) + unit


def cmd_list(_args) -> None:
    print("Scenarios:")
    for s in SCENARIOS.values():
        print(f"  {s.name:<16} {s.description}")
    print("Actions:")
    for a in ACTIONS.values():
        print(f"  {a.name:<16} {a.description}")


def cmd_run(args) -> None:
    _run(_pick(args.scenario, SCENARIOS, "scenario"), _pick(args.action, ACTIONS, "action"),
         args.reps)
    cmd_report(args)


def cmd_report(_args) -> None:
    rows = store.summary()
    if not rows:
        print("No valid trials recorded yet.")
        return
    print(f"\n{'scenario':<15} {'action':<15} {'recovered':>9} {'median':>8} "
          f"{'min-max':>13} {'availability':>12}")
    for r in rows:
        spread = f"{_fmt(r['min_s'], '.1f')}-{_fmt(r['max_s'], '.1f')}s" if r["recovered"] else "-"
        print(f"{r['scenario']:<15} {r['action']:<15} {r['recovered']:>4}/{r['trials']:<4} "
              f"{_fmt(r['median_s'], '.1f', 's'):>8} {spread:>13} {r['availability']:>12.1%}")


def cmd_gate(args) -> None:
    trials = _run(_pick(args.scenario, SCENARIOS, "scenario"),
                  _pick(args.action, ACTIONS, "action"), args.reps)
    failures = [
        t for t in trials
        if not (t.valid and t.recovered and t.recovery_time_s <= args.max_recovery)
    ]
    if failures:
        sys.exit(f"RESILIENCE GATE FAILED: {len(failures)}/{len(trials)} trials missed "
                 f"'recovered within {args.max_recovery:.0f}s'")
    print(f"RESILIENCE GATE PASSED: all {len(trials)} trials recovered within "
          f"{args.max_recovery:.0f}s")


def main() -> None:
    parser = argparse.ArgumentParser(prog="chaosctl", description="CHAOS OS experiment controller")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show scenarios and actions").set_defaults(func=cmd_list)
    sub.add_parser("report", help="summarise recorded trials").set_defaults(func=cmd_report)

    for name, func, help_text in [("run", cmd_run, "run experiments and record results"),
                                  ("gate", cmd_gate, "run experiments; exit 1 if recovery is too slow")]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--scenario", required=True, help="name, comma list, or 'all'")
        p.add_argument("--action", required=True, help="name, comma list, or 'all'")
        p.add_argument("--reps", type=int, default=1)
        if name == "gate":
            p.add_argument("--max-recovery", type=float, default=30,
                           help="seconds from injection to sustained recovery")
        p.set_defaults(func=func)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
