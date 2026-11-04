#!/bin/sh
# Share CHAOS OS from this computer at a public HTTPS address (macOS / Linux / WSL),
# behind the login in deploy/secrets.yml. No server, account or card needed.
#   ./deploy/share.sh          start sharing (prints the address)
#   ./deploy/share.sh stop     stop sharing and go back to the normal local lab
set -e
cd "$(dirname "$0")/.."
compose() {
  docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml \
    -f deploy/docker-compose.tunnel.yml "$@"
}

if [ "$1" = "stop" ]; then
  # The default files (with the local override) drop caddy and tunnel as orphans.
  docker compose up -d --wait --remove-orphans
  echo "Sharing stopped. Local dashboard: http://localhost:8090"
  exit 0
fi

[ -f deploy/secrets.yml ] || { echo "Create deploy/secrets.yml first (copy secrets.example.yml)."; exit 1; }
secret() { sed -n "s/^$1:[[:space:]]*//p" deploy/secrets.yml | tr -d "\"'" | sed 's/[[:space:]]*$//'; }
USER_NAME="$(secret dashboard_user)"
PASSWORD="$(secret dashboard_password)"
for name in dashboard_password grafana_password; do
  value="$(secret "$name")"
  if [ "${#value}" -lt 12 ] || echo "$value" | grep -q change-me; then
    echo "Set a long, real $name in deploy/secrets.yml (12+ characters)."; exit 1
  fi
done

export SITE_ADDRESS=":80"   # plain HTTP inside Docker; Cloudflare serves the HTTPS
export DASHBOARD_USER="$USER_NAME"
export DASHBOARD_PASSWORD_HASH="$(docker run --rm caddy:2.8.4-alpine caddy hash-password --plaintext "$PASSWORD")"
export GRAFANA_PASSWORD="$(secret grafana_password)"

# Start the tunnel first: Grafana needs the public address it will be served at.
compose up -d tunnel
URL=""
for _ in $(seq 30); do
  URL="$(compose logs tunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | head -1)"
  [ -n "$URL" ] && break
  sleep 2
done
[ -n "$URL" ] || { echo "No tunnel address yet; check: docker logs chaosos-tunnel-1"; exit 1; }
export PUBLIC_URL="$URL"

echo "Starting the lab behind $URL (the first run builds images)..."
compose up -d --build --wait --remove-orphans

# A new address takes a moment to reach Cloudflare's DNS.
for _ in $(seq 30); do
  curl -fsS -o /dev/null -u "$USER_NAME:$PASSWORD" "$URL/api/overview" && break
  sleep 3
done

echo
echo "CHAOS OS is shared at $URL"
echo "  Log in as '$USER_NAME' with the password in deploy/secrets.yml"
echo "  Grafana: $URL/grafana"
echo "  Online while this computer is awake. Stop: ./deploy/share.sh stop"
