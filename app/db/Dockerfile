# Config is baked into the image (not bind-mounted) so the stack also works
# when Jenkins drives Docker through the host socket.
FROM postgres:16-alpine
COPY init.sql /docker-entrypoint-initdb.d/init.sql
