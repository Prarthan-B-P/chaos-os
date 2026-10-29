# Experiment controller. Built from the repo root so it can bundle the Ansible
# playbooks it executes as recovery actions.
FROM python:3.12-slim

COPY --from=docker:27.3-cli /usr/local/bin/docker /usr/local/bin/docker
COPY controller/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY ansible /ansible
COPY controller /app
COPY resilience-gate.yml /app/resilience-gate.yml
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "chaosctl"]
