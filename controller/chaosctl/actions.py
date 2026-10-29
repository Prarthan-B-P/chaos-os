"""Recovery actions. Each maps to an Ansible playbook (or to doing nothing).

Only names listed here can be executed; the playbooks enforce the service
allowlist in ansible/group_vars/lab.yml as a second layer of safety.
"""
import subprocess
import time
from dataclasses import dataclass

from .config import ANSIBLE_DIR, LAB_PROJECT


@dataclass(frozen=True)
class Action:
    name: str
    description: str
    playbook: str | None
    extra_vars: dict[str, str]


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    duration_s: float
    output_tail: str


ACTIONS = {
    a.name: a
    for a in [
        Action("none", "Do nothing (baseline)", None, {}),
        Action("restart_redis", "Restart the Redis container",
               "playbooks/restart_service.yml", {"service": "redis"}),
        Action("cache_bypass", "Serve reads from Postgres, skipping Redis",
               "playbooks/set_cache_bypass.yml", {"enabled": "true"}),
    ]
}


def run_action(action: Action) -> ActionResult:
    if action.playbook is None:
        return ActionResult(ok=True, duration_s=0.0, output_tail="")
    cmd = ["ansible-playbook", action.playbook, "-e", f"compose_project={LAB_PROJECT}"]
    for key, value in action.extra_vars.items():
        cmd += ["-e", f"{key}={value}"]
    start = time.monotonic()
    result = subprocess.run(cmd, cwd=ANSIBLE_DIR, capture_output=True, text=True)
    tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-5:])
    return ActionResult(result.returncode == 0, time.monotonic() - start, tail)
