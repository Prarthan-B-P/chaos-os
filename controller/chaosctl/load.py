"""Open-model load generator that records every request.

Requests are sent at a fixed rate regardless of how slow responses are, so an
outage shows up as failures/latency instead of silently reducing traffic.
"""
import asyncio
import random
import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Sample:
    sent_at: float       # seconds since load start
    completed_at: float  # seconds since load start
    latency_ms: float
    status: int          # HTTP status, or 0 for timeouts / connection errors

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class LoadGenerator:
    def __init__(self, base_url: str, rate_per_s: float = 20, timeout_s: float = 2.0,
                 item_count: int = 1000):
        self.base_url = base_url
        self.rate_per_s = rate_per_s
        self.timeout_s = timeout_s
        self.item_count = item_count
        self.samples: list[Sample] = []  # appended in completion order
        self._t0 = time.monotonic()

    def now(self) -> float:
        return time.monotonic() - self._t0

    async def run(self, stop: asyncio.Event) -> None:
        self._t0 = time.monotonic()
        interval = 1 / self.rate_per_s
        in_flight: set[asyncio.Task] = set()
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s,
                                     limits=limits) as client:
            sent = 0
            while not stop.is_set():
                delay = sent * interval - self.now()
                if delay > 0:
                    try:
                        await asyncio.wait_for(stop.wait(), delay)
                        break
                    except asyncio.TimeoutError:
                        pass
                task = asyncio.create_task(self._request(client))
                in_flight.add(task)
                task.add_done_callback(in_flight.discard)
                sent += 1
            if in_flight:
                await asyncio.gather(*in_flight)

    async def _request(self, client: httpx.AsyncClient) -> None:
        sent_at = self.now()
        item_id = random.randint(1, self.item_count)
        try:
            response = await client.get(f"/items/{item_id}")
            status = response.status_code
        except httpx.HTTPError:
            status = 0
        completed_at = self.now()
        self.samples.append(
            Sample(sent_at, completed_at, (completed_at - sent_at) * 1000, status)
        )
