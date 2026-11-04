"""Turns raw request samples into recovery measurements.

Definition of "recovered" (see README, "How recovery is measured"):
time after fault injection is cut into 1 s windows by request *send* time.
A window is healthy when >= 99 % of its requests succeed and p95 latency is
<= 300 ms. The service counts as recovered once 5 consecutive healthy windows
follow the first unhealthy window. The recovery *time* is then pinned below
window resolution: the send time of the first request after the last bad
request (failed, or slower than 300 ms) before that healthy run.
"""
import math
from dataclasses import dataclass

from .load import Sample


@dataclass(frozen=True)
class RecoveryCriteria:
    window_s: float = 1.0
    min_success_rate: float = 0.99
    max_p95_ms: float = 300.0
    healthy_windows_required: int = 5


@dataclass(frozen=True)
class Analysis:
    impacted: bool                 # the fault caused at least one unhealthy window
    recovered: bool
    recovery_time_s: float | None  # injection -> start of sustained healthy period
    incident_requests: int
    incident_failures: int
    incident_availability: float   # success ratio from injection to recovery (or end)
    incident_p95_ms: float | None


def p95(latencies: list[float]) -> float | None:
    if not latencies:
        return None
    ordered = sorted(latencies)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def is_bad(s: Sample, c: RecoveryCriteria) -> bool:
    return not s.ok or s.latency_ms > c.max_p95_ms


def is_healthy(samples: list[Sample], c: RecoveryCriteria) -> bool:
    if not samples:
        return False  # no traffic getting through is not healthy
    success = sum(s.ok for s in samples) / len(samples)
    return success >= c.min_success_rate and p95([s.latency_ms for s in samples]) <= c.max_p95_ms


def window_summary(samples: list[Sample]) -> tuple[float | None, float | None]:
    """(success rate, p95 ms) for a set of samples."""
    if not samples:
        return None, None
    return sum(s.ok for s in samples) / len(samples), p95([s.latency_ms for s in samples])


def analyze(samples: list[Sample], inject_at: float, end_at: float,
            c: RecoveryCriteria) -> Analysis:
    n_windows = max(0, int((end_at - inject_at) // c.window_s))
    buckets: list[list[Sample]] = [[] for _ in range(n_windows)]
    for s in samples:
        if s.sent_at >= inject_at:
            i = int((s.sent_at - inject_at) // c.window_s)
            if i < n_windows:
                buckets[i].append(s)
    healthy = [is_healthy(b, c) for b in buckets]

    first_bad = next((i for i, ok in enumerate(healthy) if not ok), None)
    k = c.healthy_windows_required
    recovered_at: float | None
    if first_bad is None:
        recovered_at = inject_at
    else:
        recovered_idx = next(
            (i for i in range(first_bad + 1, n_windows - k + 1) if all(healthy[i:i + k])),
            None,
        )
        recovered_at = None
        if recovered_idx is not None:
            run_start = inject_at + recovered_idx * c.window_s
            before = sorted((s for b in buckets[:recovered_idx] for s in b),
                            key=lambda s: s.sent_at)
            last_bad = max((s.sent_at for s in before if is_bad(s, c)), default=None)
            recovered_at = run_start if last_bad is None else next(
                (s.sent_at for s in before if s.sent_at > last_bad), run_start)

    incident_end = end_at if recovered_at is None else recovered_at
    incident = [s for b in buckets for s in b if s.sent_at < incident_end]
    failures = sum(not s.ok for s in incident)
    return Analysis(
        impacted=first_bad is not None,
        recovered=recovered_at is not None,
        recovery_time_s=None if recovered_at is None else recovered_at - inject_at,
        incident_requests=len(incident),
        incident_failures=failures,
        incident_availability=1.0 if not incident else 1 - failures / len(incident),
        incident_p95_ms=p95([s.latency_ms for s in incident]),
    )


def recent(samples: list[Sample], now: float, c: RecoveryCriteria) -> list[Sample]:
    """Requests that *completed* in the last window (live view, no waiting for timeouts)."""
    out = []
    for s in reversed(samples):  # samples are in completion order
        if s.completed_at < now - c.window_s:
            break
        out.append(s)
    return out


def healthy_streak(samples: list[Sample], now: float, c: RecoveryCriteria,
                   windows: int = 3) -> bool:
    """Live: were the last `windows` completion windows all healthy?

    Used to decide whether a recovery step worked before trying another one.
    """
    for i in range(windows):
        lo, hi = now - (i + 1) * c.window_s, now - i * c.window_s
        if not is_healthy([s for s in samples if lo <= s.completed_at < hi], c):
            return False
    return True


def recently_unhealthy(samples: list[Sample], now: float, c: RecoveryCriteria) -> bool:
    """Live detector used to decide when to trigger a recovery action."""
    return not is_healthy(recent(samples, now, c), c)
