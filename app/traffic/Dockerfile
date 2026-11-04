# Synthetic users: steady traffic + the client-side SLI that the SLO alerts use.
FROM python:3.12-slim
RUN pip install --no-cache-dir httpx==0.27.2 prometheus-client==0.20.0
COPY traffic.py /srv/traffic.py
RUN useradd --system --uid 10001 traffic
USER traffic
ENV PYTHONUNBUFFERED=1
EXPOSE 9100
HEALTHCHECK --interval=5s --timeout=2s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9100/metrics', timeout=1)"
CMD ["python", "/srv/traffic.py"]
