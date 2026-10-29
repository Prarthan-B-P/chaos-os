"""Settings read from the environment (set in docker-compose.yml)."""
import os

API_URL = os.environ.get("API_URL", "http://api:8000")
TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474")
LAB_PROJECT = os.environ.get("LAB_PROJECT", "chaosos")
RESULTS_DB = os.environ.get("RESULTS_DB", "/results/chaos.db")
ANSIBLE_DIR = os.environ.get("ANSIBLE_DIR", "/ansible")
SAFETY_POLICY = os.environ.get("SAFETY_POLICY", "/app/safety-policy.yml")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://grafana:3000")
GRAFANA_AUTH = (os.environ.get("GRAFANA_USER", "admin"), os.environ.get("GRAFANA_PASSWORD", "admin"))
