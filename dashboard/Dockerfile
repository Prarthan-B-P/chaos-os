# Evidence Dashboard: React frontend + FastAPI backend that reuses chaosctl.
# Built from the repo root (it bundles the controller and its playbooks).
FROM node:20.18-alpine AS web
WORKDIR /web
COPY dashboard/web/package.json ./
RUN npm install --no-audit --no-fund
COPY dashboard/web ./
RUN npm run build

FROM python:3.12-slim
COPY --from=docker:27.3-cli /usr/local/bin/docker /usr/local/bin/docker
COPY controller/requirements.txt /tmp/controller.txt
COPY dashboard/requirements.txt /tmp/dashboard.txt
RUN pip install --no-cache-dir -r /tmp/controller.txt -r /tmp/dashboard.txt

COPY ansible /ansible
COPY controller /app
COPY resilience-gate.yml safety-policy.yml /app/
COPY dashboard/server /app/dashboard_server
COPY --from=web /web/dist /app/static
WORKDIR /app
ENV PYTHONUNBUFFERED=1
EXPOSE 8090
CMD ["uvicorn", "dashboard_server.app:app", "--host", "0.0.0.0", "--port", "8090"]
