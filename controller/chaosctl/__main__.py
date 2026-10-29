"""CLI.

  python -m chaosctl list
  python -m chaosctl run --scenario redis_down --action restart_redis,cache_bypass --reps 3
  python -m chaosctl run --scenario all --action all        # all = training scenarios
  python -m chaosctl report
  python -m chaosctl gate --config resilience-gate.yml
"""
import argparse
import asyncio
import sys

import yaml

from . import store
from .actions import ACTIONS
from .experiment import TrialResult, run_trial
from .scenarios import HELD_OUT, SCENARIOS, TRAINING

SCENARIO_GROUPS = {"all": TRAINING, "held_out": HELD_OUT}


def _pick(value: str, options: dict, groups: dict, kind: str) -> list:
    if value in groups:
        return list(groups[value].values())
    names = value.split(",")
    unknown = [n for n in names if n not in options]
    if unknown:
        sys.exit(f"unknown {kind}: {', '.join(unknown)} "
                 f"(choose from {', '.join([*groups, *options])})")
    return [options[n] for n in names]


def _scenarios(value: str) -> list:
    return _pick(value, SCENARIOS, SCENARIO_GROUPS, "scenario")


def _actions(value: str) -> list:
    return _pick(value, ACTIONS, {"all": ACTIONS}, "action")


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
            f"{t.incident_failures}/{t.incident_requests} requests failed")


def _run(scenarios, actions, reps: int) -> list[TrialResult]:
    results = []
    for scenario in scenarios:
        for action in actions:
            for rep in range(1, reps + 1):
                label = f"[{scenario.name} / {action.name} #{rep}]"
                print(f"{label} running...", flush=True)
                trial = asyncio.run(run_trial(scenario, action))
                store.save(trial)
                print(f"{label} {_describe(trial)}", flush=True)
                results.append(trial)
    return results


def _fmt(x: float | None, spec: str, unit: str = "") -> str:
    return "-" if x is None else format(x, spec) + unit


def cmd_list(_args) -> None:
    print("Scenarios:")
    for s in SCENARIOS.values():
        print(f"  {s.name:<20} {s.description}{'  [held out]' if s.held_out else ''}")
    print("Actions:")
    for a in ACTIONS.values():
        print(f"  {a.name:<20} {a.description}")


def cmd_run(args) -> None:
    _run(_scenarios(args.scenario), _actions(args.action), args.reps)
    cmd_report(args)


def cmd_report(_args) -> None:
    rows = store.summary()
    if not rows:
        print("No valid trials recorded yet.")
        return
    print(f"\n{'scenario':<19} {'action':<17} {'recovered':>9} {'median':>8} "
          f"{'min-max':>11} {'failed req':>10}")
    for r in rows:
        spread = f"{_fmt(r['min_s'], '.1f')}-{_fmt(r['max_s'], '.1f')}s" if r["recovered"] else "-"
        print(f"{r['scenario']:<19} {r['action']:<17} {r['recovered']:>4}/{r['trials']:<4} "
              f"{_fmt(r['median_s'], '.1f', 's'):>8} {spread:>11} {r['failed_requests']:>10.0f}")


def cmd_gate(args) -> None:
    with open(args.config) as f:
        checks = yaml.safe_load(f)["checks"]

    failures = 0
    for check in checks:
        limit = float(check["max_recovery_s"])
        trials = _run(_scenarios(check["scenario"]), _actions(check["action"]),
                      int(check.get("reps", 1)))
        for t in trials:
            passed = t.valid and t.recovered and t.recovery_time_s <= limit
            failures += not passed
            print(f"  {'PASS' if passed else 'FAIL'}: {t.scenario} -> {t.action} "
                  f"must recover within {limit:.0f}s "
                  f"(got {_fmt(t.recovery_time_s, '.1f', 's') if t.recovered else 'no recovery'})",
                  flush=True)

    if failures:
        sys.exit(f"RESILIENCE GATE FAILED: {failures} check(s) missed their recovery limit")
    print("RESILIENCE GATE PASSED")


def main() -> None:
    parser = argparse.ArgumentParser(prog="chaosctl", description="CHAOS OS experiment controller")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show scenarios and actions").set_defaults(func=cmd_list)
    sub.add_parser("report", help="summarise recorded trials").set_defaults(func=cmd_report)

    run = sub.add_parser("run", help="run experiments and record results")
    run.add_argument("--scenario", required=True,
                     help="name, comma list, 'all' (training) or 'held_out'")
    run.add_argument("--action", required=True, help="name, comma list, or 'all'")
    run.add_argument("--reps", type=int, default=1)
    run.set_defaults(func=cmd_run)

    gate = sub.add_parser("gate", help="run the checks in a gate file; exit 1 on any failure")
    gate.add_argument("--config", default="resilience-gate.yml")
    gate.set_defaults(func=cmd_gate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
