"""Failure scenarios. Each one knows how to inject its fault; lab.reset()
clears every fault after a trial.

Held-out scenarios are never used to develop or train policies. They exist
to test whether a policy generalizes to failures it has not seen (Phase 6).
"""
from collections.abc import Callable
from dataclasses import dataclass

from . import lab


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    inject: Callable[[], None]
    held_out: bool = False


def _kill(service: str) -> Callable[[], None]:
    return lambda: lab.docker("kill", *lab.containers(service))


def _latency(proxy: str, ms: int) -> Callable[[], None]:
    return lambda: lab.toxiproxy("POST", f"/proxies/{proxy}/toxics", {
        "name": "latency", "type": "latency", "stream": "downstream",
        "attributes": {"latency": ms, "jitter": 0},
    })


def _partition(proxy: str) -> Callable[[], None]:
    return lambda: lab.toxiproxy("POST", f"/proxies/{proxy}", {"enabled": False})


def _both(*faults: Callable[[], None]) -> Callable[[], None]:
    def inject() -> None:
        for fault in faults:
            fault()
    return inject


SCENARIOS = {
    s.name: s
    for s in [
        Scenario("redis_down", "Redis container is killed", _kill("redis")),
        # 800 ms is above the API's 500 ms Redis timeout, so cache calls fail.
        Scenario("redis_latency", "800 ms latency between API and Redis",
                 _latency("redis", 800)),
        # 400 ms per query pushes cache misses past the 300 ms p95 limit.
        Scenario("postgres_latency", "400 ms latency between API and Postgres",
                 _latency("postgres", 400)),
        Scenario("postgres_down", "Postgres container is killed", _kill("postgres")),
        Scenario("api_crash", "API container is killed", _kill("api")),

        # Held out: Redis unreachable like redis_down, but the container is fine,
        # so restarting it does nothing.
        Scenario("redis_partition", "Network path to Redis is cut",
                 _partition("redis"), held_out=True),
        # Held out: compound fault where cache bypass would pile load on a slow DB.
        Scenario("redis_down_slow_db", "Redis killed while Postgres has 400 ms latency",
                 _both(_kill("redis"), _latency("postgres", 400)), held_out=True),
    ]
}

TRAINING = {name: s for name, s in SCENARIOS.items() if not s.held_out}
HELD_OUT = {name: s for name, s in SCENARIOS.items() if s.held_out}
