"""Smoke test for the CHAOS OS lab. Standard library only.

Usage:
    python scripts/smoke_test.py [BASE_URL]      (default http://localhost:8080)

Jenkins pipes this file into a throwaway container on the stack's network,
so it must not import anything outside the standard library.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
READY_TIMEOUT_SECONDS = 60


def get(path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def wait_until_ready() -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while True:
        try:
            status, body = get("/api/ready")
            if status == 200:
                print(f"ready: {body}")
                return
            print(f"not ready yet ({status}): {body}")
        except (urllib.error.URLError, ConnectionError) as err:
            print(f"not reachable yet: {err}")
        if time.monotonic() > deadline:
            sys.exit(f"FAIL: stack not ready after {READY_TIMEOUT_SECONDS}s")
        time.sleep(2)


def main() -> None:
    wait_until_ready()

    status, first = get("/api/items/42")
    assert status == 200, f"expected 200 for item 42, got {status}: {first}"

    status, second = get("/api/items/42")
    assert status == 200, f"expected 200 on repeat read, got {status}: {second}"
    assert second["source"] == "cache", f"expected cache hit on repeat read, got {second}"

    status, _ = get("/api/items/999999")
    assert status == 404, f"expected 404 for missing item, got {status}"

    print("PASS: smoke test")


if __name__ == "__main__":
    main()
