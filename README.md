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

`--scenario` and `--action` take a name, a comma list, or `all`.

Each trial: reset the lab → 15 s warm-up under load (20 req/s) → inject the
fault → detect the outage → run the recovery action → measure → reset.
Trials whose warm-up baseline is not healthy are marked invalid and excluded.

| Scenario | Fault |
|---|---|
| `redis_down` | Redis container is killed |
| `redis_latency` | 800 ms latency between API and Redis (Toxiproxy) |

| Action | Playbook |
|---|---|
| `none` | nothing - the baseline |
| `restart_redis` | `restart_service.yml -e service=redis` |
| `cache_bypass` | `set_cache_bypass.yml -e enabled=true` |

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
(the needed plugins are pre-installed), and create an admin user. Then create a
**Pipeline** job → *Pipeline script from SCM* → Git → your repository URL →
branch `*/main` → script path `Jenkinsfile`.

CI runs its own copy of the lab (`chaosos-ci`, no host ports), so it never
touches a lab you have running locally. The **resilience gate** fails the build
if any gated scenario takes longer than 10 s to recover.

## Optional: OpenAI

Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Used from Phase 5 for
report explanations and as an extra policy to benchmark. Nothing requires it.

## Roadmap

- [x] **Phase 1** - App, health checks, Prometheus/Grafana, Toxiproxy wiring, Jenkins, Ansible
- [x] **Phase 2** - Load generator, recovery definition, first measured experiments, CI gate
- [ ] **Phase 3** - More fault scenarios (Postgres, API crash, combined faults)
- [ ] **Phase 4** - More recovery playbooks (scale, rollback), safety validator in the controller
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
