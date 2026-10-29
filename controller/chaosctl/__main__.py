"""CLI.

  python -m chaosctl list
  python -m chaosctl run --scenario all --action all --reps 2         # fixed-action matrix
  python -m chaosctl run --scenario held_out --policy heuristic,bandit --timeout 90
  python -m chaosctl train                                             # fit the bandit
  python -m chaosctl learning-curve
  python -m chaosctl report --by policy
  python -m chaosctl explain [--trial ID]                              # AI write-up
  python -m chaosctl gate --config resilience-gate.yml
"""
import argparse
import sys

import yaml

from . import insights, learning, store
from .actions import ACTIONS
from .experiment import TrialResult
from .policies import POLICIES
from .runner import make_policy, run_one
from .scenarios import HELD_OUT, SCENARIOS, TRAINING

SCENARIO_GROUPS = {"all": TRAINING, "held_out": HELD_OUT}


def _pick(value: str, options: dict, groups: dict, kind: str) -> list:
    if value in groups:
        return list(groups[value])
    names = value.split(",")
    unknown = [n for n in names if n not in options]
    if unknown:
        sys.exit(f"unknown {kind}: {', '.join(unknown)} "
                 f"(choose from {', '.join([*groups, *options])})")
    return names


def _describe(t: TrialResult) -> str:
    if not t.valid:
        return f"INVALID baseline (success={t.baseline_success}, p95={t.baseline_p95_ms} ms)"
    if not t.impacted:
        return "fault had no measurable impact"
    outcome = (f"recovered in {t.recovery_time_s:.1f}s" if t.recovered
               else "did NOT recover within the timeout")
    ran = t.actions or "nothing"
    blocked = f", blocked: {t.blocked}" if t.blocked else ""
    return f"{outcome}; ran: {ran}{blocked}; {t.incident_failures}/{t.incident_requests} failed"


def _run(scenarios: list[str], runs: list[tuple[str, dict]], reps: int,
         timeout_s: float) -> list[TrialResult]:
    """runs: (label, make_policy kwargs) pairs."""
    results = []
    for scenario in scenarios:
        for label, kwargs in runs:
            for rep in range(1, reps + 1):
                tag = f"[{scenario} / {label} #{rep}]"
                print(f"{tag} running...", flush=True)
                _, trial = run_one(SCENARIOS[scenario], make_policy(**kwargs), timeout_s)
                print(f"{tag} {_describe(trial)}", flush=True)
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
    print("Policies:")
    for name, p in POLICIES.items():
        print(f"  {name:<20} {(p.__doc__ or '').strip().splitlines()[0]}")


def cmd_run(args) -> None:
    if bool(args.action) == bool(args.policy):
        sys.exit("give exactly one of --action or --policy")
    if args.action:
        runs = [(a, {"action": a}) for a in _pick(args.action, ACTIONS, {"all": ACTIONS}, "action")]
    else:
        runs = [(p, {"policy": p}) for p in _pick(args.policy, POLICIES, {}, "policy")]
    try:
        _run(_pick(args.scenario, SCENARIOS, SCENARIO_GROUPS, "scenario"), runs, args.reps,
             args.timeout)
    except RuntimeError as exc:
        sys.exit(str(exc))
    args.by = "action" if args.action else "policy"
    cmd_report(args)


def cmd_report(args) -> None:
    rows = store.summary(args.by)
    if not rows:
        print("No valid trials recorded yet.")
        return
    print(f"\n{'scenario':<19} {args.by:<17} {'recovered':>9} {'median':>8} "
          f"{'min-max':>11} {'failed req':>10} {'blocked':>7}")
    for r in rows:
        spread = f"{_fmt(r['min_s'], '.1f')}-{_fmt(r['max_s'], '.1f')}s" if r["recovered"] else "-"
        print(f"{r['scenario']:<19} {r[args.by]:<17} {r['recovered']:>4}/{r['trials']:<4} "
              f"{_fmt(r['median_s'], '.1f', 's'):>8} {spread:>11} "
              f"{r['failed_requests']:>10.0f} {r['safety_blocked']:>7}")


def cmd_train(_args) -> None:
    model, n = learning.train()
    print(f"Trained LinUCB on {n} steps from training scenarios only.")
    lc = learning.learning_curve(points=2, permutations=1)
    for scenario, action in sorted(lc.get("best", {}).items()):
        print(f"  best measured action for {scenario:<17} {action}")


def cmd_learning_curve(_args) -> None:
    lc = learning.learning_curve()
    print(f"Replay over {lc['steps']} logged steps (30 random orders):")
    print(f"{'steps seen':>10} {'accuracy':>9} {'regret':>7}")
    for p in lc["curve"]:
        print(f"{p['steps_seen']:>10} {p['accuracy']:>9.0%} {p['regret']:>7.3f}")
    for name, b in lc["baselines"].items():
        print(f"{name:>10} {b['accuracy']:>9.0%} {b['regret']:>7.3f}   (fixed rules)")


def cmd_explain(args) -> None:
    try:
        text = (insights.explain_trial(args.trial, args.refresh) if args.trial
                else insights.explain_results(args.refresh))
    except (RuntimeError, ValueError) as exc:
        sys.exit(str(exc))
    print(text)


def cmd_gate(args) -> None:
    with open(args.config) as f:
        checks = yaml.safe_load(f)["checks"]

    failures = 0
    for check in checks:
        limit = float(check["max_recovery_s"])
        trials = _run([check["scenario"]], [(check["action"], {"action": check["action"]})],
                      int(check.get("reps", 1)), 60)
        for t in trials:
            passed = t.valid and t.recovered and t.recovery_time_s <= limit
            failures += not passed
            got = _fmt(t.recovery_time_s, ".1f", "s") if t.recovered else "no recovery"
            print(f"  {'PASS' if passed else 'FAIL'}: {t.scenario} -> {check['action']} "
                  f"must recover within {limit:.0f}s (got {got})", flush=True)

    if failures:
        sys.exit(f"RESILIENCE GATE FAILED: {failures} check(s) missed their recovery limit")
    print("RESILIENCE GATE PASSED")


def main() -> None:
    parser = argparse.ArgumentParser(prog="chaosctl", description="CHAOS OS experiment controller")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show scenarios, actions and policies").set_defaults(func=cmd_list)

    run = sub.add_parser("run", help="run experiments and record results")
    run.add_argument("--scenario", required=True,
                     help="name, comma list, 'all' (training) or 'held_out'")
    run.add_argument("--action", help="fixed action(s): name, comma list, or 'all'")
    run.add_argument("--policy", help="policy name(s), comma separated")
    run.add_argument("--reps", type=int, default=1)
    run.add_argument("--timeout", type=float, default=60, help="seconds after injection")
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report", help="summarise recorded trials")
    report.add_argument("--by", choices=["action", "policy"], default="action")
    report.set_defaults(func=cmd_report)

    sub.add_parser("train", help="fit the bandit on training scenarios").set_defaults(func=cmd_train)
    sub.add_parser("learning-curve", help="bandit accuracy vs. experience") \
        .set_defaults(func=cmd_learning_curve)

    explain = sub.add_parser("explain", help="AI write-up of results or one trial (gpt-4o-mini)")
    explain.add_argument("--trial", type=int)
    explain.add_argument("--refresh", action="store_true")
    explain.set_defaults(func=cmd_explain)

    gate = sub.add_parser("gate", help="run the checks in a gate file; exit 1 on any failure")
    gate.add_argument("--config", default="resilience-gate.yml")
    gate.set_defaults(func=cmd_gate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
