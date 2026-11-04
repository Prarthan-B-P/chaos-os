# Demo runbook

A 7-minute live demo of CHAOS OS, plus answers to likely questions. The full
team guide (with about 50 viva questions) is in
[docs/study-guide](study-guide/).

## 10 minutes before

1. Start **Docker Desktop** and wait until it says *Engine running*.
2. Start the lab and Jenkins:
   ```powershell
   docker compose up -d --wait
   docker compose -f jenkins/docker-compose.yml up -d --wait
   ```
3. Open five browser tabs:
   - Dashboard: http://localhost:8090 (On-call page: http://localhost:8090/#/oncall)
   - Grafana: http://localhost:3000/d/chaos-os-service-health (admin / admin)
   - Alertmanager: http://localhost:9093
   - Jenkins: http://localhost:8081/job/chaos-os-ci/
   - GitHub: https://github.com/Prarthan-B-P/chaos-os
4. Warm up: on the **On-call** page, **Break it** once with `redis_down` and let
   the agent heal it, so the live demo is not the first incident after a cold start.
5. Check the strip at the top of the dashboard says **healthy** and the On-call
   page says **Autopilot on**. If not, click **Reset lab** on the Overview.

## The 7 minutes

| Time | Do | Say |
|---|---|---|
| 0:00 | Dashboard → Overview | "Everything here is measured: experiments, recovery, blocked unsafe actions." |
| 0:40 | On-call → Failure: *Surprise me* → **Break it** | "I just broke the shop. The agent was not told what or when." |
| 1:00 | Watch the incident timeline fill in | "Users noticed, the SLO burned 14 times too fast, Alertmanager paged the agent, it confirmed with its own traffic, picked a fix, the safety validator allowed it." |
| 2:00 | Open the incident → post-mortem | "gpt-4o-mini wrote this from the incident record only." |
| 2:45 | **Break it** with `postgres_down` → **Approve** on the orange card | "Restarting the database is high impact, so the agent asks me. No answer in 60 seconds means it does nothing." |
| 3:45 | Incidents → an *LLM agent + tools* trial → open the tool trail | "The agent investigated with real tools (metrics, logs) before deciding; every call is auditable." |
| 4:30 | Grafana → *SLO and on-call* row | "The burn rate crosses the 14.4 line; the orange markers are our fault and fix." |
| 5:15 | Jenkins → `main` (green) vs `demo/broken-cache-bypass` (red) | "A one-character bug passed unit and smoke tests. The resilience gate blocked it. Every build also scans for secrets and CVEs and runs an unannounced on-call drill." |
| 6:15 | Overview → **Ask the lab** (Ctrl+K) | Let someone ask, e.g. "Which fix works best for a slow database?" |

## If something goes wrong

- **No internet or OpenAI down:** skip the post-mortem and Ask the lab; everything else is local.
- **The lab looks broken:** Overview → **Reset lab**, or `docker compose up -d --wait`.
- **"The lab is busy":** an experiment or an on-call incident owns the lab; wait (at most about 2 minutes).
- **No page after Break it:** check http://localhost:9090/targets (traffic must be *up*) and Alertmanager.
- **Jenkins not reachable:** show the screenshots in the study guide.

## Likely questions

The full list with model answers is in the study guide (chapter 10). The five
most likely:

**How do you define "recovered"?**
Five consecutive 1-second windows with at least 99 % successful requests and p95
latency of 300 ms or less, measured per request by the load generator.

**Isn't the bandit just memorizing failure names?**
It never sees the name, only symptoms. The held-out Redis network cut proves it:
never trained on, it looks like "Redis down", and the bandit still picked the
right fix (3/3, 0.8 s) while the runbook failed 0/3.

**What stops the AI from doing something dangerous?**
It only proposes. The safety validator checks every proposal (approved lab,
allowlist, no repeats, at most three actions, approval for high impact) and the
Ansible playbooks enforce their own allowlist. Zero unsafe actions ever executed.

**What did the LLM ablation show?**
Advice changed the habit, not the reasoning: with one paragraph of generic SRE
guidance the model chose cache bypass first in all 14 trials, so Redis latency
fell from 50 s to 3.3 s, but a crashed database was never restarted. Tools alone
added 8-12 s without changing choices; tools plus advice handled both kinds of
fault (10/14, the best LLM result). See the README and the paper.

**How does the on-call agent know something is wrong?**
It is never told. Synthetic users measure the SLO, Prometheus pages on a
multi-window burn rate, and the agent confirms with its own probe traffic before
acting.
