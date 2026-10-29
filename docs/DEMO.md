# Demo runbook

A 5-minute live demo of CHAOS OS, plus answers to likely questions.

## 10 minutes before

1. Start **Docker Desktop** and wait until it says *Engine running*.
2. Start the lab and dashboard:
   ```powershell
   docker compose up -d --wait
   docker compose -f jenkins/docker-compose.yml up -d --wait
   ```
3. Open four browser tabs:
   - Dashboard: http://localhost:8090
   - Grafana: http://localhost:3000/d/chaos-os-service-health (log in admin / admin)
   - Jenkins: http://localhost:8081/job/chaos-os-ci/
   - GitHub: https://github.com/Prarthan-B-P/chaos-os
4. Warm up: on the dashboard **Run** page, run *redis_latency* with *Bandit (learned)*
   once, so the live demo is not the first experiment after a cold start.
5. Check the strip at the top of the dashboard says **healthy · 7/7 services up**.
   If not, click **Reset lab** on the Overview.

## The 5 minutes

| Time | Do | Say |
|---|---|---|
| 0:00 | Dashboard Overview | "Everything here is measured: experiments, recovery rate, blocked unsafe actions." |
| 0:45 | **Run** → failure `redis_latency`, responder **Bandit (learned)** → Start | "Redis just got slow. Watch: outage detected, the bandit picks cache bypass, the validator approves, recovered in about 3 seconds." |
| 2:00 | Click **Incident #…** → **Write post-mortem** | "Every incident is a timeline of what it saw and did. gpt-4o-mini writes the post-mortem from the measured data." |
| 3:00 | Grafana tab | "The orange markers are the fault injection and the fix, on the live metrics." |
| 3:45 | Jenkins → `demo/broken-cache-bypass` (red) vs `main` (green) | "A one-character bug passed unit and smoke tests. The resilience gate blocked it." |
| 4:30 | Overview → **Ask the lab** (Ctrl+K) | Let someone ask, e.g. "Which fix works best for a slow database?" |

## If something goes wrong

- **No internet or OpenAI down:** skip Ask the lab and the post-mortem; everything else is local.
- **A run is stuck or the lab looks broken:** Overview → **Reset lab**, or
  `docker compose up -d --wait`.
- **Dashboard shows "another experiment is already running":** wait for it to
  finish (at most about 2 minutes); only one experiment runs at a time on purpose.
- **Jenkins not reachable:** show the green and red builds from the deck (slide 12).

## Likely questions

**Why not just use an existing chaos tool (Chaos Mesh, LitmusChaos, Gremlin)?**
They inject faults; they don't compare recovery strategies or learn which one
to use. CHAOS OS measures every fix against every failure, learns from it, and
gates releases on the result. A Kubernetes port with Chaos Mesh as the fault
injector is listed as future work.

**Isn't the bandit just memorizing failure names?**
It never sees the name. Its input is observable symptoms only (error rate,
p95, API up, Redis/Postgres reachability and probe latency). The held-out
Redis network cut is the proof: it was never trained on, looks like "Redis
down", and the bandit still picked the right fix (3/3, 0.8 s).

**Why does the heuristic do as well as the bandit?**
I wrote the heuristic after studying the training results, so it encodes the
answers. The bandit reaches the same level without anyone writing rules, which
is what matters when there are many more failures than a person can study.

**How do you define "recovered"?**
Five consecutive 1-second windows with at least 99 % successful requests and p95
latency of 300 ms or less, measured per request by the load generator.
Prometheus scrapes every 5 s, which is too coarse for second-level recovery.

**What stops the AI from doing something dangerous?**
Every action, from any policy, passes the safety validator first: approved lab
environments only, an action allowlist, no repeats (no restart loops), at most
three actions per incident, and approval for high-impact actions. Ansible adds
a second allowlist. The red-team policy proposed `drop_database` and
`restart_grafana`; both were blocked. Zero unsafe actions ever executed.

**Why did the LLM do worse?**
It tends to try a restart first, which wastes about 40 s when restarting
cannot help, and it never fixed the slow database. It is still useful for
explaining results, where it only summarizes measured data.

**How many trials? Is that enough?**
Two per pair for training failures, three for held-out ones, plus the
fixed-action matrix. Enough to show clear differences (0/2 vs 2/2), not enough
for confidence intervals; that is listed as a limitation and next step.

**What would you do next?**
Multi-step policies for compound failures (the 0/12 case), more trials with
confidence intervals, a Kubernetes port, and online bandit training in CI.
