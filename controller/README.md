# chaosctl

Experiment controller: generates load, injects a fault, runs a recovery
playbook, and measures recovery. Runs as the `controller` compose service.

```powershell
docker compose run --rm --build controller list
docker compose run --rm controller run --scenario redis_down --action all --reps 3
docker compose run --rm controller report
```

| Module | Role |
|---|---|
| `load.py` | fixed-rate load generator, records every request |
| `analysis.py` | recovery definition and measurements |
| `scenarios.py` | fault injection (Docker, Toxiproxy) |
| `actions.py` | recovery actions -> Ansible playbooks |
| `experiment.py` | one trial, end to end |
| `store.py` | SQLite history (`/results/chaos.db`) |
