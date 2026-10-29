"""Settings read from the environment (set in docker-compose.yml)."""
import os

API_URL = os.environ.get("API_URL", "http://api:8000")
TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474")
LAB_PROJECT = os.environ.get("LAB_PROJECT", "chaosos")
RESULTS_DB = os.environ.get("RESULTS_DB", "/results/chaos.db")
ANSIBLE_DIR = os.environ.get("ANSIBLE_DIR", "/ansible")
