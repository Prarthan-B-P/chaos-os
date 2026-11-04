"""Measure on-call mode: unannounced faults, one at a time, through the dashboard API.

    python scripts/oncall_campaign.py --reps 3 --policy heuristic

For every failure scenario the script breaks the lab without telling the agent
(POST /api/oncall/break), waits for the agent's incident to finish, plays a
human operator who approves high-impact actions after a fixed reaction time,
then resets the lab and waits for the SLO alert to clear before the next fault.
Results come from the agent's own records (the dashboard's scorecard), so this
script only drives and waits. Standard library only.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

FINISHED = ("resolved", "escalated")


def call(base: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, method="POST" if data else "GET",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def retry_busy(base: str, path: str, body: dict, timeout_s: float = 60) -> dict:
    """POST, retrying while the lab is busy (409): the agent may still hold the lab lock
    for a moment after it records the outcome."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return call(base, path, body)
        except urllib.error.HTTPError as err:
            if err.code != 409 or time.monotonic() > deadline:
                raise
            time.sleep(2)


def wait_quiet(base: str, settle_s: float = 5, timeout_s: float = 300) -> None:
    """Steady state before every fault: no alert firing, no incident open, and no bad
    requests left in the 1-minute SLO window (residue would give the next alert a head start)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = call(base, "/api/oncall")
        burn = status["slo"]["burn_1m"]
        if not status["alerts"] and not status["active"] and (burn is None or burn < 0.01):
            time.sleep(settle_s)
            return
        time.sleep(3)
    print("  (no steady state after the cool-down; continuing)", flush=True)


def run_fault(base: str, scenario: str, approve_after_s: float, timeout_s: float) -> dict:
    before = call(base, "/api/oncall")["incidents"]
    last_id = before[0]["id"] if before else 0
    event = retry_busy(base, "/api/oncall/break", {"scenario": scenario})
    deadline = time.monotonic() + timeout_s
    approvals = 0
    incident = None
    while time.monotonic() < deadline:
        status = call(base, "/api/oncall")
        pending = status["approval"]
        if pending and pending["incident_id"] > last_id:
            time.sleep(approve_after_s)  # the operator reads the card, then clicks Approve
            try:
                call(base, f"/api/oncall/approvals/{pending['id']}", {"approve": True})
                approvals += 1
            except urllib.error.HTTPError:
                pass  # expired or already decided
        new = [i for i in status["incidents"] if i["id"] > last_id]
        if new and new[-1]["status"] in FINISHED:
            incident = new[-1]
            break
        time.sleep(1)
    retry_busy(base, "/api/lab/reset", {})  # the fault is rolled back whatever happened
    score = next((m for m in call(base, "/api/oncall")["score"]["matches"]
                  if m["event"]["id"] == event["id"]), {})
    return {"scenario": scenario, "event_id": event["id"],
            "incident_id": incident and incident["id"],
            "status": incident["status"] if incident else "no incident",
            "actions": incident and incident["actions"], "blocked": incident and incident["blocked"],
            "approvals": approvals, "mitigation_s": incident and incident["mitigation_s"],
            "detect_s": score.get("detect_s"), "engage_s": score.get("engage_s"),
            "recover_s": score.get("recover_s")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://localhost:8090")
    parser.add_argument("--policy", default="heuristic")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--scenarios", default="redis_down,redis_latency,postgres_latency,"
                        "postgres_down,api_crash,redis_partition,redis_down_slow_db")
    parser.add_argument("--approve-after", type=float, default=5.0, help="operator reaction time (s)")
    parser.add_argument("--timeout", type=float, default=300, help="per fault (s)")
    parser.add_argument("--out", default="oncall-campaign.json")
    args = parser.parse_args()

    call(args.base, "/api/oncall/settings", {"autopilot": True, "policy": args.policy, "monkey": False})
    retry_busy(args.base, "/api/lab/reset", {})
    wait_quiet(args.base)
    results = []
    for rep in range(1, args.reps + 1):
        for scenario in args.scenarios.split(","):
            print(f"[{scenario} #{rep}] breaking the lab (unannounced)...", flush=True)
            r = run_fault(args.base, scenario, args.approve_after, args.timeout)
            r.update(policy=args.policy, rep=rep)
            results.append(r)
            print(f"  -> {r['status']}: alert +{r['detect_s']}s, agent +{r['engage_s']}s, healthy "
                  f"+{r['recover_s']}s, ran {r['actions'] or '-'}"
                  f"{', blocked ' + r['blocked'] if r['blocked'] else ''}", flush=True)
            with open(args.out, "w") as f:
                json.dump(results, f, indent=2)
            wait_quiet(args.base)
    healed = sum(r["status"] == "resolved" for r in results)
    print(f"done: {healed}/{len(results)} unannounced faults healed; results in {args.out}")
    sys.exit(0)


if __name__ == "__main__":
    main()
