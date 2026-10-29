"""Unit tests for the recovery definition. Run: python -m unittest discover -s tests"""
import unittest

from chaosctl.analysis import RecoveryCriteria, analyze, recently_unhealthy
from chaosctl.load import Sample

C = RecoveryCriteria()
INJECT = 10.0


def traffic(start: float, end: float, outcome, rate: float = 20) -> list[Sample]:
    """Synthetic samples; outcome(t) -> (status, latency_ms)."""
    samples, t = [], start
    while t < end:
        status, latency = outcome(t)
        samples.append(Sample(t, t + latency / 1000, latency, status))
        t = round(t + 1 / rate, 6)
    return samples


class AnalyzeTests(unittest.TestCase):
    def test_no_impact_counts_as_immediate_recovery(self):
        a = analyze(traffic(0, 30, lambda t: (200, 10)), INJECT, 30, C)
        self.assertFalse(a.impacted)
        self.assertTrue(a.recovered)
        self.assertEqual(a.recovery_time_s, 0)
        self.assertEqual(a.incident_availability, 1.0)

    def test_recovery_time_is_first_request_after_last_failure(self):
        # Errors from injection until t=13.2, healthy afterwards.
        samples = traffic(0, 30, lambda t: (503, 5) if INJECT <= t < 13.2 else (200, 10))
        a = analyze(samples, INJECT, 30, C)
        self.assertTrue(a.impacted)
        self.assertTrue(a.recovered)
        self.assertAlmostEqual(a.recovery_time_s, 3.2, places=2)
        self.assertEqual(a.incident_failures, a.incident_requests)  # all incident requests failed

    def test_slow_requests_count_as_unhealthy(self):
        samples = traffic(0, 30, lambda t: (200, 800) if INJECT <= t < 12 else (200, 10))
        a = analyze(samples, INJECT, 30, C)
        self.assertTrue(a.impacted)
        self.assertAlmostEqual(a.recovery_time_s, 2.0, places=2)
        self.assertEqual(a.incident_failures, 0)  # slow, but not failed

    def test_never_recovers(self):
        samples = traffic(0, 30, lambda t: (503, 5) if t >= INJECT else (200, 10))
        a = analyze(samples, INJECT, 30, C)
        self.assertTrue(a.impacted)
        self.assertFalse(a.recovered)
        self.assertIsNone(a.recovery_time_s)
        self.assertEqual(a.incident_availability, 0.0)

    def test_short_healthy_blip_is_not_recovery(self):
        # Healthy for only 2 s in the middle (needs 5), then truly recovers at t=20.
        def outcome(t):
            if INJECT <= t < 13 or 15 <= t < 20:
                return 503, 5
            return 200, 10
        a = analyze(traffic(0, 40, outcome), INJECT, 40, C)
        self.assertAlmostEqual(a.recovery_time_s, 10.0, places=2)


class LiveDetectorTests(unittest.TestCase):
    def test_detects_recent_failures(self):
        samples = traffic(0, 12, lambda t: (503, 5) if t >= 11 else (200, 10))
        self.assertTrue(recently_unhealthy(samples, 12.0, C))

    def test_healthy_traffic_is_not_flagged(self):
        samples = traffic(0, 12, lambda t: (200, 10))
        self.assertFalse(recently_unhealthy(samples, 12.0, C))


if __name__ == "__main__":
    unittest.main()
