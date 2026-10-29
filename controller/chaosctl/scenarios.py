"""Failure scenarios. Each one knows how to inject its fault; lab.reset()
clears every fault after a trial."""
from collections.abc import Callable
from dataclasses import dataclass

from . import lab


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    inject: Callable[[], None]


def _kill_redis() -> None:
    lab.docker("kill", *lab.containers("redis"))


def _add_redis_latency() -> None:
    # 800 ms is above the API's 500 ms Redis timeout, so cache calls fail.
    lab.toxiproxy("POST", "/proxies/redis/toxics", {
        "name": "latency", "type": "latency", "stream": "downstream",
        "attributes": {"latency": 800, "jitter": 0},
    })


SCENARIOS = {
    s.name: s
    for s in [
        Scenario("redis_down", "Redis container is killed", _kill_redis),
        Scenario("redis_latency", "800 ms latency between API and Redis", _add_redis_latency),
    ]
}
