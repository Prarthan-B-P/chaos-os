"""Talks to the lab: Docker containers, Toxiproxy, and the API's admin endpoints."""
import subprocess
import time

import httpx

from .config import API_URL, LAB_PROJECT, TOXIPROXY_URL


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def containers(service: str | None = None, status: str | None = None) -> list[str]:
    """IDs of this lab's long-running containers (excludes `compose run` tools)."""
    filters = [
        "--filter", f"label=com.docker.compose.project={LAB_PROJECT}",
        "--filter", "label=com.docker.compose.oneoff=False",
    ]
    if service:
        filters += ["--filter", f"label=com.docker.compose.service={service}"]
    if status:
        filters += ["--filter", f"status={status}"]
    return docker("ps", "-aq", *filters).split()


def toxiproxy(method: str, path: str, json: dict | None = None) -> None:
    httpx.request(method, f"{TOXIPROXY_URL}{path}", json=json, timeout=5).raise_for_status()


def probe() -> dict:
    """What an operator could observe right now via the API's readiness check.

    Policies must decide from observations like these, never from the name of
    the injected fault.
    """
    try:
        body = httpx.get(f"{API_URL}/ready", timeout=2).json()
        return {"api_up": True, "redis_ok": body["redis"], "postgres_ok": body["postgres"],
                "redis_ms": body["redis_ms"], "postgres_ms": body["postgres_ms"]}
    except (httpx.HTTPError, ValueError, KeyError):
        return {"api_up": False, "redis_ok": None, "postgres_ok": None,
                "redis_ms": None, "postgres_ms": None}


def wait_until_ready(timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{API_URL}/ready", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError(f"lab not ready after {timeout_s:.0f}s")


def reset() -> None:
    """Put the lab back into a known-good state before every trial."""
    toxiproxy("POST", "/reset")  # re-enables all proxies and removes all toxics
    stopped = containers(status="exited")
    if stopped:
        docker("start", *stopped)
    wait_until_ready()
    httpx.post(f"{API_URL}/admin/cache-bypass", json={"enabled": False}, timeout=5).raise_for_status()
    for redis_id in containers("redis"):
        docker("exec", redis_id, "redis-cli", "FLUSHALL")  # every trial starts with a cold cache
