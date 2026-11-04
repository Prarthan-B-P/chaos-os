#!/bin/sh
# Deploy (or update) CHAOS OS on your server (macOS / Linux / WSL).
#   ./deploy/deploy.sh 129.1.2.3 [user] [private-key]
set -e
SERVER="${1:?usage: deploy.sh <server-ip> [user] [private-key]}"
USER_NAME="${2:-ubuntu}"
KEY="${3:-$HOME/.ssh/id_ed25519}"
DIR="$(cd "$(dirname "$0")" && pwd)"

[ -f "$DIR/secrets.yml" ] || { echo "Create deploy/secrets.yml first (copy secrets.example.yml)."; exit 1; }
[ -f "$KEY" ] || { echo "SSH private key not found: $KEY"; exit 1; }

docker build -q -t chaosos-deployer "$DIR/runner" >/dev/null
docker run --rm -it -v "$KEY:/keys/id:ro" -v "$DIR:/deploy" \
  chaosos-deployer -i "$SERVER," -u "$USER_NAME" deploy.yml
