# CHAOS OS

*Break it. Learn from it. Build infrastructure that survives it.*

A local lab that injects infrastructure failures into a small application,
runs competing recovery strategies, measures which one works best, and gates
releases on the results.

## Architecture

```
            ┌──────────┐      ┌─────────┐     ┌───────────┐     ┌──────────┐
 browser ──►│ frontend │─────►│   api   │────►│ toxiproxy │────►│  redis   │
            │  nginx   │      │ FastAPI │     │ (faults)  │────►│ postgres │
            └──────────┘      └────┬────┘     └───────────┘     └──────────┘
                 ▲                 │ /metrics
                 │          ┌──────▼─────┐    ┌─────────┐
                 │          │ prometheus │───►│ grafana │
     load +      │          └────────────┘    └─────────┘
     faults  ┌───┴────────┐
             │ controller │── runs Ansible recovery playbooks (allowlisted)
             │ (chaosctl) │── stores every trial in SQLite
             └────────────┘
 jenkins (separate) ── build → unit tests → deploy → smoke → resilience gate → teardown
```

The API reaches Redis and Postgres **through Toxiproxy**, so latency and
outages can be injected without touching the services themselves.

## Prerequisites

- Docker Desktop (WSL2 backend), 8 GB+ allocated
- Python 3.10+ (only for running the smoke test from the host)
- Git

## Quick start

```powershell
docker compose up -d --build --wait     # start the lab
python scripts/smoke_test.py            # should print PASS
```

| Service | URL |
|---|---|
| Demo frontend | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana (dashboard: CHAOS OS → Service Health) | http://localhost:3000 (admin / admin) |
| Toxiproxy API | http://localhost:8474/proxies |
| Jenkins | http://localhost:8081 |

Stop with `docker compose down`. `down -v` also wipes the database **and the
experiment history**.

## Running experiments

```powershell
docker compose run --rm --build controller list          # scenarios and actions
docker compose run --rm controller run --scenario redis_down --action all --reps 3
docker compose run --rm controller report                # summary of all trials
```

`--scenario` takes a name, a comma list, `all` (training scenarios) or
`held_out`. `--action` takes a name, a comma list, or `all`.

Each trial: reset the lab → 15 s warm-up under load (20 req/s) → inject the
fault → detect the outage → record symptoms → run the recovery action →
measure → reset. Trials whose warm-up baseline is not healthy are marked
invalid and excluded.

| Scenario | Fault | Set |
|---|---|---|
| `redis_down` | Redis container is killed | training |
| `redis_latency` | 800 ms latency between API and Redis | training |
| `postgres_latency` | 400 ms latency between API and Postgres | training |
| `postgres_down` | Postgres container is killed | training |
| `api_crash` | API container is killed | training |
| `redis_partition` | network path to Redis cut (container healthy) | **held out** |
| `redis_down_slow_db` | Redis killed + 400 ms Postgres latency | **held out** |

Held-out scenarios are never used to develop or train policies; they test
whether a policy generalizes to failures it has not seen.

| Action | Playbook |
|---|---|
| `none` | nothing - the baseline |
| `restart_redis` / `restart_postgres` / `restart_api` | `restart_service.yml -e service=<name>` |
| `cache_bypass` | `set_cache_bypass.yml -e enabled=true` |
| `warm_cache` | `warm_cache.yml -e ttl_seconds=600` |

**Symptoms.** At detection time each trial records what an operator could
observe: error rate, p95 latency, whether the API answers, and Redis/Postgres
reachability and probe latency (from `/ready`). Policies must choose actions
from these symptoms - never from the injected fault's name.

### Results so far (training scenarios)

Full matrix, 1-4 trials per pair. Recovery time is the median; failed
requests are per trial (at 20 req/s, a 60 s outage is ~1200).

| Failure | Best action | Recovery | Failed req | Every other action |
|---|---|---|---|---|
| `redis_down` | `cache_bypass` | 1.3 s | ~25 | `restart_redis` also works (2.5 s, ~42); rest fail |
| `redis_latency` | `cache_bypass` | 1.2 s | ~26 | all fail, incl. `restart_redis` |
| `postgres_latency` | `warm_cache` | 7.4 s | ~107 | all fail; `cache_bypass` makes it worse |
| `postgres_down` | `restart_postgres` | 7.3 s | ~74 | all fail |
| `api_crash` | `restart_api` | 9.8 s | ~157 | all fail |

No single rule works everywhere: picking the wrong action costs ~1200 failed
requests instead of ~25-160. Held-out scenarios have deliberately **not**
been run yet, so no policy can be tuned on them.

Findings along the way:
- `warm_cache` first failed on a slow database: traffic exhausted the
  connection pool and the fix queued behind it. It now uses a dedicated
  connection - recovery work must not share resources with the failure.
- Prometheus (5 s scrapes, 30 s rate windows) is too coarse for second-level
  recovery, so recovery is measured per request by the load generator.

### How recovery is measured

Defined in [controller/chaosctl/analysis.py](controller/chaosctl/analysis.py)
and covered by unit tests.

- Time after injection is split into **1 s windows** by request send time.
- A window is **healthy** when **≥ 99 %** of requests succeed **and p95
  latency ≤ 300 ms**. A window with no completed requests is unhealthy.
- The service has **recovered** once **5 consecutive healthy windows** follow
  the first unhealthy one. A brief healthy blip does not count.
- **Recovery time** = injection → the first request after the last bad
  request (failed or > 300 ms) preceding that healthy run.
- **Availability** = share of successful requests from injection to recovery.
- Trials time out 60 s after injection.

## Recovery actions (Ansible)

Ansible runs in a container on the lab network, so no WSL setup is needed.
The controller calls the same playbooks.

```powershell
docker compose run --rm --build ansible playbooks/set_cache_bypass.yml -e enabled=true
docker compose run --rm ansible playbooks/restart_service.yml -e service=redis
```

Every playbook checks `allowed_services` in `ansible/group_vars/lab.yml`
and refuses anything else (try `-e service=grafana`).

## Jenkins

```powershell
docker compose -f jenkins/docker-compose.yml up -d --build --wait
docker exec chaosos-jenkins-jenkins-1 cat /var/jenkins_home/secrets/initialAdminPassword
```

Open http://localhost:8081, paste the password, choose **Select plugins → None**
(the needed plugins are pre-installed), and create an admin user.

The **chaos-os-ci** multibranch job is defined as code in
[jenkins/jobs/chaos-os-ci/config.xml](jenkins/jobs/chaos-os-ci/config.xml) and
baked into the Jenkins image. It builds every branch and polls GitHub every
5 minutes (webhooks can't reach localhost).

Each build runs its own copy of the lab (`chaosos-ci-<executor>`, no host
ports), so parallel branch builds never touch each other or your local lab.

### Resilience gate

[resilience-gate.yml](resilience-gate.yml) lists the failures every release
must survive, the playbook to use, and the recovery deadline. Any miss fails
the build.

**Proof it works:** branch `demo/broken-cache-bypass` contains a one-character
bug - the cache-bypass endpoint writes the wrong flag key, returns 200, and the
Ansible playbook reports success, yet nothing changes. Unit tests and the smoke
test pass; the resilience gate fails the build (both cache-bypass trials never
recover), while `main` stays green.

## Optional: OpenAI

Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Used from Phase 5 for
report explanations and as an extra policy to benchmark. Nothing requires it.

## Roadmap

- [x] **Phase 1** - App, health checks, Prometheus/Grafana, Toxiproxy wiring, Jenkins, Ansible
- [x] **Phase 2** - Load generator, recovery definition, first measured experiments, CI gate
- [x] **Phase 3** - Postgres/API faults, held-out scenarios, symptom capture, gate as code, multibranch CI
- [ ] **Phase 4** - Safety validator in the controller, more playbooks (scale, rollback)
- [ ] **Phase 5** - Strategy tournament, rule-based vs. contextual bandit (+ optional LLM policy)
- [ ] **Phase 6** - Held-out failure scenarios, safety-violation tests
- [ ] **Phase 7** - Generated HTML reports, Grafana experiment annotations
- [ ] **Phase 8** - Benchmarks and write-up

## Project layout

```
app/            target application (api, frontend, db)
chaos/          fault injection (Toxiproxy config)
controller/     chaosctl: load generator, experiments, analysis, results
observability/  Prometheus and Grafana config + dashboards
ansible/        recovery playbooks and safety allowlist
jenkins/        Jenkins image and compose file
scripts/        smoke test
Jenkinsfile     CI pipeline
```
