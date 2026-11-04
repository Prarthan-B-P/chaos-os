"""Synthetic users: steady background traffic, and the SLI measured where users are.

A service is judged by what its users experience, so the shop's SLO is measured
here, at the client, not inside the API (which can't count requests it never
received, e.g. while it is down). A request is "good" when it succeeds within
300 ms: the same line the experiments draw. Prometheus scrapes these counters;
the burn-rate alerts in observability/prometheus/rules/slo.yml are built on them.
"""
import asyncio
import os
import random
import time

import httpx
from prometheus_client import Counter, Histogram, start_http_server

API_URL = os.environ.get("API_URL", "http://api:8000")
RATE_PER_S = float(os.environ.get("TRAFFIC_RATE", "2"))
GOOD_WITHIN_S = 0.3
ITEMS = 1000

REQUESTS = Counter("shop_synthetic_requests_total", "Synthetic user requests by result",
                   ["result"])  # good | slow (succeeded, > 300 ms) | error
LATENCY = Histogram("shop_synthetic_request_duration_seconds", "Synthetic user request latency",
                    buckets=(0.025, 0.05, 0.1, 0.3, 0.5, 1, 2))


async def visit(client: httpx.AsyncClient) -> None:
    start = time.perf_counter()
    try:
        ok = (await client.get(f"/items/{random.randint(1, ITEMS)}")).status_code == 200
    except httpx.HTTPError:
        ok = False
    elapsed = time.perf_counter() - start
    LATENCY.observe(elapsed)
    REQUESTS.labels("good" if ok and elapsed <= GOOD_WITHIN_S else "slow" if ok else "error").inc()


async def main() -> None:
    start_http_server(9100)
    for result in ("good", "slow", "error"):
        REQUESTS.labels(result)  # export zeros, so ratios exist before the first failure
    in_flight: set[asyncio.Task] = set()
    async with httpx.AsyncClient(base_url=API_URL, timeout=2) as client:
        next_at = time.monotonic()
        while True:
            # Open model: users keep arriving on schedule, however slow the replies.
            task = asyncio.create_task(visit(client))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
            next_at += 1 / RATE_PER_S
            await asyncio.sleep(max(0.0, next_at - time.monotonic()))


if __name__ == "__main__":
    asyncio.run(main())
