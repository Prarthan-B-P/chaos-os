# CHAOS OS

*Break it. Learn from it. Build infrastructure that survives it.*

CHAOS OS is a local resilience lab. It injects real failures into a small web
shop running under steady load, lets competing **recovery policies** choose
what to do, checks every proposed action against a **safety validator**,
measures recovery **request by request**, and gates releases in **Jenkins** on
the results. A contextual bandit learns which fix works for which symptoms,
and gpt-4o-mini explains the evidence in plain English.

**Headline results (all measured, see [Results](#results)):**

- **No single fix works everywhere.** Each of the 5 training failures has a
  different best action; picking the wrong one costs 450–1,100 failed requests
  instead of 30–250.
- **The learned policy (LinUCB bandit) reaches 98 % best-action accuracy** from
  52 logged experiments, against 40 % for a conventional "restart what looks
  broken" runbook. It equals the hand-written expert rules, without anyone
  writing its rules.
- **It generalizes to an unseen failure.** On a held-out Redis network cut the
  bandit recovered 3/3 in 0.8 s, while the runbook failed 3/3 and the LLM took 43 s.
- **It does not solve compound failures.** No policy recovered from "Redis
  killed + slow database" (0/12). That is the clearest limitation.
- **The safety validator blocked every unsafe proposal**; zero unsafe actions
  ever executed.
- **The CI gate catches a bug that unit and smoke tests miss** (see
  [Resilience gate](#resilience-gate)).

---

## Architecture

```
                         ┌──────────┐    ┌─────────┐    ┌───────────┐    ┌──────────┐
             browser ───►│ frontend │───►│   api   │───►│ toxiproxy │───►│  redis   │
                         │  nginx   │    │ FastAPI │    │ (faults)  │───►│ postgres │
                         └──────────┘    └────┬────┘    └───────────┘    └──────────┘
                              ▲               │ /metrics, /ready
     load (20 req/s)          │        ┌──────▼─────┐   ┌─────────┐
     + faults          ┌──────┴─────┐  │ prometheus │──►│ grafana │◄── annotations
                       │ controller │  └────────────┘   └─────────┘
                       │ (chaosctl) │── policy proposes ─► safety validator ─► Ansible playbook
                       └──────┬─────┘
                              │ SQLite: every trial and every step
              ┌───────────────┴──────────────┐
              │ evidence dashboard (React)   │── gpt-4o-mini: Q&A, analysis, post-mortems
              └──────────────────────────────┘
  jenkins (separate) ── build → unit tests → deploy → smoke → resilience gate → report → teardown
```

The API reaches Redis and Postgres **through Toxiproxy**, so latency and
outages can be injected without touching the services themselves.

## How an experiment works

Every trial is a small incident, handled the way an on-call engineer would:

1. **Reset** the lab to a known-good state (faults cleared, cache flushed).
2. **Warm up** for 15 s at 20 req/s; trials with an unhealthy baseline are discarded.
3. **Inject** the fault and **detect** the outage from live traffic.
4. **Remediation loop** (at most 3 actions):
   observe symptoms → the policy proposes an action → the **safety validator**
   allows or blocks it → the action runs as an **Ansible playbook** → wait up
   to 20 s for the service to heal → repeat if it did not.
5. **Measure** recovery and save the trial and each step to SQLite.

**Recovery definition** ([analysis.py](controller/chaosctl/analysis.py), unit-tested):
time is split into 1 s windows; a window is healthy when ≥ 99 % of requests
succeed and p95 ≤ 300 ms. The service has recovered after 5 consecutive
healthy windows. Recovery time runs from fault injection to the first request
after the last bad one. Prometheus (5 s scrapes) is too coarse for this, so
the load generator measures every request itself.

**Symptoms, not answers.** Policies only see what an operator could observe:
error rate, p95 latency, whether the API answers, and Redis/Postgres
reachability and probe latency. They never see the name of the injected fault.

### Failures

| Failure | Fault | Set |
|---|---|---|
| `redis_down` | Redis container killed | training |
| `redis_latency` | 800 ms latency to Redis | training |
| `postgres_latency` | 400 ms latency to Postgres | training |
| `postgres_down` | Postgres container killed | training |
| `api_crash` | API container killed | training |
| `redis_partition` | network path to Redis cut, container healthy | **held out** |
| `redis_down_slow_db` | Redis killed + 400 ms Postgres latency | **held out** |

Held-out failures were never used to design or train anything, and were run
only once the policies were frozen.

### Recovery actions (Ansible playbooks)

| Action | What it does | Safety impact |
|---|---|---|
| `restart_redis` / `restart_api` | restart the container, wait for `/ready` | medium |
| `restart_postgres` | restart the database | **high** (needs approval) |
| `cache_bypass` | serve reads from Postgres, skipping Redis | low |
| `warm_cache` | preload all items into Redis with one query | low |

### Policies

| Policy | How it decides |
|---|---|
| `rule_based` | Conventional runbook: restart whatever looks broken, then restart the app |
| `heuristic` | Expert rules written from the measured characteristics of each failure |
| `bandit` | LinUCB contextual bandit trained on logged steps; reward = heal speed − safety cost |
| `llm` | gpt-4o-mini reads the symptoms and picks an action (still safety-checked) |
| `adversarial` | Red-team policy that proposes unsafe actions on purpose |

---

## Results

All numbers below come from the experiment database. Load is 20 req/s, so a
60 s outage is about 1,200 failed requests.

### 1. Every failure needs a different fix (fixed-action matrix, 2 trials each)

| Failure | Best action | Recovery | Failed req | Other actions |
|---|---|---|---|---|
| `redis_down` | `cache_bypass` | 1.8 s | 34 | `restart_redis` also works (2.0 s); rest never recover |
| `redis_latency` | `cache_bypass` | 1.9 s | 38 | all others fail, **including `restart_redis`** |
| `postgres_latency` | `warm_cache` | 9.0 s | 116 | all others fail; `cache_bypass` makes it worse |
| `postgres_down` | `restart_postgres` | 6.9 s | 76 | all others fail |
| `api_crash` | `restart_api` | 14.6 s | 252 | all others fail |

### 2. Policies on the training failures (2 trials each)

| Failure | Rule-based | Heuristic | Bandit | LLM |
|---|---|---|---|---|
| `redis_down` | ✓ 2.9 s | ✓ 1.6 s | ✓ **1.6 s** | ✓ 4.0 s |
| `redis_latency` | ✕ 0/2 | ✓ 2.8 s | ✓ **2.7 s** | ✓ 28.9 s (5–53 s) |
| `postgres_latency` | ✕ 0/2 | ✓ 9.8 s | ✓ 32.7 s (10–55 s) | ✕ 0/2 |
| `postgres_down` | ✓ 7.4 s | ✓ 8.0 s | ✓ 43.2 s (8–79 s) | ✓ 12.0 s |
| `api_crash` | ✓ 16.1 s | ✓ 16.0 s | ✓ 16.0 s | ✓ 16.1 s |
| **Recovered** | **6/10** | **10/10** | **10/10** | **8/10** |

The runbook fails exactly where "restart it" is the wrong answer. The bandit
matches the expert rules on recovery rate. Its two slow outliers came from a
first step that a slow database can provoke (connection timeouts look like a
dead database), after which a second action fixed it. The LLM often tried a
restart first, which costs about 40 s before falling back to the right fix.

### 3. Generalization to held-out failures (3 trials each)

| Held-out failure | Rule-based | Heuristic | Bandit | LLM |
|---|---|---|---|---|
| `redis_partition` | ✕ 0/3 | ✓ 3/3, 0.9 s | ✓ **3/3, 0.8 s** | ✓ 3/3, 43.4 s |
| `redis_down_slow_db` | ✕ 0/3 | ✕ 0/3 | ✕ 0/3 | ✕ 0/3 |

The partition looks like `redis_down` to every policy, but restarting Redis
does nothing because the container is healthy. The bandit learned to answer
"Redis unreachable" with `cache_bypass` rather than a restart, so it
generalized. The compound failure needs two coordinated fixes (restart Redis
*and* warm the cache, without bypass); no policy found that combination.

### 4. Learning curve

The bandit is replayed over the 52 logged training steps in 30 random orders
and scored on how often it picks the best measured action:

| Steps seen | 0 | 14 | 24 | 33 | 52 |
|---|---|---|---|---|---|
| Bandit accuracy | 0 % | 62 % | 78 % | 92 % | **98 %** |

Fixed baselines: rule-based runbook **40 %**, expert heuristic **98 %**.

### 5. Safety

- Red-team run 1 (`redis_down`): the adversarial policy proposed
  `drop_database` and `restart_grafana`. **Both were blocked**; only the
  allowlisted `restart_redis` ran.
- Red-team run 2 (`redis_latency`, where restarts cannot help, so the policy
  keeps escalating): `drop_database` was blocked as an unknown action,
  `restart_grafana` as not allowlisted, and a second `restart_redis` as a
  repeat (no restart loops). The high-impact `restart_postgres` ran only
  because the lab is in `auto` approval mode; with
  `CHAOS_HIGH_IMPACT_APPROVAL=deny` it is refused (unit-tested).
- Across every experiment, **0 unsafe actions executed**. The validator
  enforces approved environments, an action allowlist, no repeats within an
  incident (no restart loops), a 3-action budget, and approval for
  high-impact actions. It is covered by 10 unit tests.

### Resilience gate

[resilience-gate.yml](resilience-gate.yml) lists the failures every release
must survive and the deadline for each. Jenkins runs it on every branch.

Branch `demo/broken-cache-bypass` contains a one-character bug: the
cache-bypass endpoint writes the wrong flag key, returns 200, and the Ansible
playbook reports success, but nothing changes. **Unit tests and the smoke test
pass; the resilience gate fails the build** (both cache-bypass checks never
recover) while `main` stays green.

### Limitations

- **Compound failures are unsolved.** Policies pick one action per step from
  single-fault experience; coordinated multi-step fixes need sequence-aware
  learning.
- **Symptom ambiguity.** A slow database can look like a dead one (pool
  timeouts), which caused the bandit's two slow outliers.
- **Small samples.** 2–3 trials per pair; ranges are shown, but there are no
  confidence intervals.
- **One lab, one machine.** Docker Desktop on a laptop; timings include
  probing and Ansible overhead, and absolute numbers will differ elsewhere.
- **Expert rules were written after seeing the training data**, which is why
  the heuristic is so strong. The bandit's value is reaching the same level
  without hand-written rules.

---

## Quick start

Prerequisites: Docker Desktop (WSL2 backend, 8 GB+), Git. Python 3.10+ only for
the host smoke test.

```powershell
docker compose up -d --build --wait     # lab + evidence dashboard
python scripts/smoke_test.py            # should print PASS
```

| Service | URL |
|---|---|
| **Evidence dashboard** | http://localhost:8090 |
| Jenkins | http://localhost:8081 |
| Grafana (CHAOS OS → Service Health) | http://localhost:3000 (admin / admin) |
| Prometheus | http://localhost:9090 |
| Demo shop | http://localhost:8080 |
| API docs | http://localhost:8000/docs |

`docker compose down` stops the lab. `down -v` also wipes the database **and
the experiment history**.

### Reproduce the results

```powershell
# 1. Fixed-action matrix = bandit training data
docker compose run --rm controller run --scenario all --action restart_redis,restart_postgres,restart_api,cache_bypass,warm_cache --reps 2 --timeout 30
# 2. Train the bandit (training failures only) and inspect the learning curve
docker compose run --rm controller train
docker compose run --rm controller learning-curve
# 3. Compare policies, then the held-out generalization test
docker compose run --rm controller run --scenario all --policy rule_based,heuristic,bandit,llm --reps 2 --timeout 90
docker compose run --rm controller run --scenario held_out --policy rule_based,heuristic,bandit,llm --reps 3 --timeout 90
# 4. Red-team the safety validator
docker compose run --rm controller run --scenario redis_down --policy adversarial
# Summaries
docker compose run --rm controller report --by action
docker compose run --rm controller report --by policy
```

Experiments can also be launched from the dashboard (**Run** page). A lab lock
ensures only one experiment runs at a time, from the CLI or the dashboard.

### Gen AI (optional)

Put your key in the git-ignored `.env` file:

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

This enables the `llm` policy, **Ask the lab** (questions answered from the
measured data), the AI results analysis, and per-incident post-mortems. The
model only summarizes data passed to it. Without a key, everything else works.

### Jenkins

```powershell
docker compose -f jenkins/docker-compose.yml up -d --build --wait
docker exec chaosos-jenkins-jenkins-1 cat /var/jenkins_home/secrets/initialAdminPassword
```

Unlock Jenkins at http://localhost:8081 (plugins: **None**, they are
pre-installed). The **chaos-os-ci** multibranch job is defined as code in
[jenkins/jobs/chaos-os-ci/config.xml](jenkins/jobs/chaos-os-ci/config.xml),
builds every branch, and polls GitHub every 5 minutes. Each build gets its own
isolated lab (`chaosos-ci-<executor>`, no host ports) and archives a
resilience report.

---

## Project layout

```
app/              target application (api, frontend, db)
chaos/            Toxiproxy config
controller/       chaosctl: load, experiments, analysis, safety, policies, bandit, gen AI
dashboard/        evidence dashboard: React frontend + FastAPI backend
ansible/          recovery playbooks + service allowlist
observability/    Prometheus and Grafana (dashboard + experiment annotations)
jenkins/          Jenkins image and job-as-code
safety-policy.yml safety rules every action is checked against
resilience-gate.yml  release gate checks
Jenkinsfile       CI pipeline
```

## Roadmap

- [x] Phase 1: app, health checks, Prometheus/Grafana, Toxiproxy, Jenkins, Ansible
- [x] Phase 2: load generator, recovery definition, measured experiments, CI gate
- [x] Phase 3: Postgres/API faults, held-out failures, symptoms, gate as code, multibranch CI
- [x] Phase 4: safety validator, remediation loop, red-team policy
- [x] Phase 5: rule-based vs. heuristic vs. contextual bandit vs. LLM
- [x] Phase 6: held-out generalization and safety evaluation
- [x] Phase 7: evidence dashboard, gen-AI insights, Grafana annotations, CI report
- [x] Phase 8: results and write-up

**Future work:** sequence-aware policies for compound failures, more trials
with confidence intervals, a Kubernetes port with Chaos Mesh, and online
(exploring) bandit training in CI.
