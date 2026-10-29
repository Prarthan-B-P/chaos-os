"""Shared entry point for running trials (used by the CLI and the dashboard)."""
import asyncio
import contextlib
import fcntl
import os

from . import store
from .config import LAB_PROJECT, RESULTS_DB, SAFETY_POLICY
from .experiment import TrialResult, run_trial
from .policies import POLICIES, FixedPolicy
from .safety import SafetyValidator
from .scenarios import Scenario


def make_policy(policy: str | None = None, action: str | None = None):
    if action is not None:
        return FixedPolicy(action)
    if policy not in POLICIES:
        raise ValueError(f"unknown policy '{policy}' (choose from {', '.join(POLICIES)})")
    return POLICIES[policy]()


def validator() -> SafetyValidator:
    return SafetyValidator.from_file(SAFETY_POLICY, LAB_PROJECT)


class LabBusy(RuntimeError):
    pass


@contextlib.contextmanager
def lab_lock(wait: bool = True):
    """One experiment at a time per lab, across the CLI and the dashboard.

    The lock file lives on the shared results volume, so separate containers see it.
    """
    path = os.path.join(os.path.dirname(RESULTS_DB), f"{LAB_PROJECT}.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            raise LabBusy("another experiment is already running on this lab") from None
        yield


def run_one(scenario: Scenario, policy, timeout_s: float = 60, on_event=None,
            wait_for_lab: bool = True) -> tuple[int, TrialResult]:
    with lab_lock(wait_for_lab):
        trial = asyncio.run(run_trial(scenario, policy, validator(), timeout_s=timeout_s,
                                      on_event=on_event))
    return store.save(trial), trial
