# How to start CHAOS OS

## The quick way (Windows)

1. Double-click **`start.bat`** in the project folder.
2. Wait. It starts Docker Desktop if needed, starts the lab and Jenkins, and
   opens the dashboard, the On-call console, Grafana and Jenkins in your browser.
   The first start builds images and takes a few minutes; later starts take
   about 30 seconds.
3. To stop, double-click **`stop.bat`**. Nothing is deleted; your experiment
   history and Jenkins data stay.

## What you need (one time)

- **Docker Desktop** installed (WSL2 backend), with 8 GB RAM or more for it.
- The project folder (`git clone https://github.com/Prarthan-B-P/chaos-os.git`).
- Optional: an OpenAI key in a file named `.env` in the project folder, for the
  AI features (LLM responders, post-mortems, Ask the lab):
  ```
  OPENAI_API_KEY=sk-...
  OPENAI_MODEL=gpt-4o-mini
  ```
  Without it, everything else works.

## The same steps by hand (any OS)

```powershell
docker compose up -d --build --wait                    # the lab, dashboard and on-call agent
docker compose -f jenkins/docker-compose.yml up -d     # Jenkins (optional)
python scripts/smoke_test.py                           # should print PASS
```

| Open | Address |
|---|---|
| Evidence dashboard | http://localhost:8090 |
| On-call console | http://localhost:8090/#/oncall |
| Grafana (admin / admin) | http://localhost:3000 |
| Jenkins | http://localhost:8081 |
| Prometheus / Alertmanager | http://localhost:9090 / http://localhost:9093 |
| Shop | http://localhost:8080 |

Stop with `docker compose stop` (and `docker compose -f jenkins/docker-compose.yml stop`).

## First things to try

1. **On-call console** → Failure: *Surprise me* → **Break it**. Watch the agent get
   paged, confirm, fix it and write a post-mortem (about 25 s).
2. **Break it** with `postgres_down` → click **Approve** on the orange card.
3. **Run** page → pick a failure and a responder → **Start experiment**.
4. **Overview** → **Ask the lab** (Ctrl+K) → ask a question about the results.

## If something goes wrong

| Problem | Fix |
|---|---|
| `start.bat` says Docker did not start | Open Docker Desktop yourself, wait for "Engine running", run `start.bat` again |
| Dashboard says "the lab is busy" | An experiment or incident is running; wait up to 2 minutes |
| Top bar says "fault active" | Dashboard → Overview → **Reset lab** |
| Port 8080 already in use | Close the other program using it |
| AI features say "unavailable" | Put `OPENAI_API_KEY` in `.env`, then run `start.bat` again |

**Never run `docker compose down -v`**: `-v` deletes the experiment history.

More: [README](README.md) · [demo runbook](docs/DEMO.md) · team study guide in
`docs/study-guide/` · deployment in [deploy/README.md](deploy/README.md).
