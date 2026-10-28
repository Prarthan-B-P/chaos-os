# CHAOS OS

*Break it. Learn from it. Build infrastructure that survives it.*

A local lab that injects infrastructure failures into a small application,
runs competing recovery strategies, measures which one works best, and gates
releases on the results.

## Architecture (current: Phase 1)

```
            ┌──────────┐      ┌─────────┐     ┌───────────┐     ┌──────────┐
 browser ──►│ frontend │─────►│   api   │────►│ toxiproxy │────►│  redis   │
            │  nginx   │      │ FastAPI │     │ (faults)  │────►│ postgres │
            └──────────┘      └────┬────┘     └───────────┘     └──────────┘
                                   │ /metrics
                            ┌──────▼─────┐    ┌─────────┐
                            │ prometheus │───►│ grafana │
                            └────────────┘    └─────────┘

 ansible (on demand) ── recovery playbooks, guarded by a service allowlist
 jenkins (separate)  ── build → deploy → smoke test → resilience gate → teardown
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

Stop with `docker compose down` (add `-v` to also wipe the database).

## Try a failure by hand

```powershell
# Cut the API off from Redis
curl.exe -X POST localhost:8474/proxies/redis -d '{\"enabled\":false}'
curl.exe localhost:8000/ready                     # -> degraded, 503

# Recover with an Ansible playbook: serve reads straight from Postgres
docker compose run --rm --build ansible playbooks/set_cache_bypass.yml -e enabled=true
curl.exe localhost:8000/items/5                   # -> 200, "source": "db"

# Restore
curl.exe -X POST localhost:8474/proxies/redis -d '{\"enabled\":true}'
docker compose run --rm ansible playbooks/set_cache_bypass.yml -e enabled=false
```

## Recovery actions (Ansible)

Ansible runs in a container on the lab network, so no WSL setup is needed.

| Playbook | What it does |
|---|---|
| `restart_service.yml -e service=<name>` | Restarts a service, waits for `/ready` |
| `set_cache_bypass.yml -e enabled=<bool>` | Serves reads from Postgres, skipping Redis |

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
script path `Jenkinsfile`.

## Optional: OpenAI

Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Used from Phase 5 for
report explanations and as an extra policy to benchmark. Nothing requires it.

## Roadmap

- [x] **Phase 1** - App, health checks, Prometheus/Grafana, Toxiproxy wiring, Jenkins, Ansible
- [ ] **Phase 2** - Load generator (k6) and a precise recovery-time definition
- [ ] **Phase 3** - Chaos runner: scripted fault scenarios, results stored in SQLite
- [ ] **Phase 4** - Recovery controller + more playbooks (scale, rollback)
- [ ] **Phase 5** - Strategy tournament, rule-based vs. contextual bandit (+ optional LLM policy)
- [ ] **Phase 6** - Held-out failure scenarios, safety-violation tests
- [ ] **Phase 7** - Resilience gate in Jenkins, generated reports
- [ ] **Phase 8** - Benchmarks and write-up

## Project layout

```
app/            target application (api, frontend, db)
chaos/          fault injection (Toxiproxy config; chaos runner from Phase 3)
observability/  Prometheus and Grafana config + dashboards
ansible/        recovery playbooks and safety allowlist
jenkins/        Jenkins image and compose file
controller/     experiment runner / learning engine (Phase 3+)
scripts/        smoke test and helpers
Jenkinsfile     CI pipeline
```
