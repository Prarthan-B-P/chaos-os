# Unprivileged nginx: runs as the nginx user (uid 101) and listens on 8080, so
# nothing in this container runs as root. OS packages are upgraded at build
# time so security fixes land even between base-image releases.
FROM nginxinc/nginx-unprivileged:1.30-alpine
USER root
RUN apk upgrade --no-cache
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
USER 101
HEALTHCHECK --interval=5s --timeout=2s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/nginx-health || exit 1
