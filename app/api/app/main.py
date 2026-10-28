"""Demo API for CHAOS OS experiments.

Reads items through a Redis cache backed by PostgreSQL. Both dependencies are
reached through Toxiproxy so faults (latency, outages) can be injected later.
"""
import json
import os
import time

import psycopg
import redis
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "60"))

app = FastAPI(title="CHAOS OS demo API")

# Short timeouts so failures surface quickly instead of hanging requests.
cache = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    socket_timeout=0.5,
    socket_connect_timeout=0.5,
)
db_pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=10,
    timeout=2,
    kwargs={"connect_timeout": 2, "options": "-c statement_timeout=2000"},
    open=False,
)

# Runtime flag flipped by recovery playbooks (e.g. serve from DB when Redis is down).
flags = {"cache_bypass": os.environ.get("CACHE_BYPASS", "false").lower() == "true"}

REQUESTS = Counter("api_requests_total", "HTTP requests", ["endpoint", "status"])
LATENCY = Histogram(
    "api_request_duration_seconds",
    "HTTP request latency",
    ["endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
CACHE_RESULTS = Counter("api_cache_total", "Cache lookups", ["result"])
DEPENDENCY_UP = Gauge("api_dependency_up", "Dependency reachable (1) or not (0)", ["dependency"])
CACHE_BYPASS = Gauge("api_cache_bypass_enabled", "Cache bypass flag")


@app.on_event("startup")
def startup() -> None:
    db_pool.open(wait=False)
    CACHE_BYPASS.set(int(flags["cache_bypass"]))


@app.on_event("shutdown")
def shutdown() -> None:
    db_pool.close()


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # Use the route template (/items/{item_id}) to keep label cardinality low.
        endpoint = getattr(request.scope.get("route"), "path", request.url.path)
        if endpoint != "/metrics":
            LATENCY.labels(endpoint).observe(time.perf_counter() - start)
            REQUESTS.labels(endpoint, str(status)).inc()


def check_redis() -> bool:
    try:
        cache.ping()
        DEPENDENCY_UP.labels("redis").set(1)
        return True
    except redis.RedisError:
        DEPENDENCY_UP.labels("redis").set(0)
        return False


def check_postgres() -> bool:
    try:
        with db_pool.connection() as conn:
            conn.execute("SELECT 1")
        DEPENDENCY_UP.labels("postgres").set(1)
        return True
    except Exception:
        DEPENDENCY_UP.labels("postgres").set(0)
        return False


@app.get("/health")
def health() -> dict:
    """Liveness: the process is up. Does not check dependencies."""
    return {"status": "ok"}


@app.get("/ready")
def ready(response: Response) -> dict:
    """Readiness: dependencies needed to serve traffic are reachable."""
    redis_ok = flags["cache_bypass"] or check_redis()
    postgres_ok = check_postgres()
    ok = redis_ok and postgres_ok
    if not ok:
        response.status_code = 503
    return {
        "status": "ready" if ok else "degraded",
        "redis": redis_ok,
        "postgres": postgres_ok,
        "cache_bypass": flags["cache_bypass"],
    }


def load_item_from_db(item_id: int) -> dict | None:
    with db_pool.connection() as conn:
        row = conn.execute(
            "SELECT id, name, price FROM items WHERE id = %s", (item_id,)
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "price": float(row[2])}


@app.get("/items/{item_id}")
def get_item(item_id: int) -> dict:
    key = f"item:{item_id}"

    if not flags["cache_bypass"]:
        try:
            cached = cache.get(key)
        except redis.RedisError:
            CACHE_RESULTS.labels("error").inc()
            raise HTTPException(status_code=503, detail="cache unavailable")
        if cached is not None:
            CACHE_RESULTS.labels("hit").inc()
            return {**json.loads(cached), "source": "cache"}
        CACHE_RESULTS.labels("miss").inc()

    try:
        item = load_item_from_db(item_id)
    except (psycopg.Error, Exception) as exc:  # pool timeouts raise PoolTimeout
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")

    if not flags["cache_bypass"]:
        try:
            cache.setex(key, CACHE_TTL_SECONDS, json.dumps(item))
        except redis.RedisError:
            pass  # Serving the response matters more than warming the cache.

    return {**item, "source": "db"}


class CacheBypassRequest(BaseModel):
    enabled: bool


@app.get("/admin/flags")
def get_flags() -> dict:
    return flags


@app.post("/admin/cache-bypass")
def set_cache_bypass(body: CacheBypassRequest) -> dict:
    flags["cache_bypass"] = body.enabled
    CACHE_BYPASS.set(int(body.enabled))
    return flags


@app.get("/metrics")
def metrics() -> Response:
    check_redis()
    check_postgres()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
