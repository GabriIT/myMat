#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
ENV_FILE="$DEPLOY_DIR/.env.vps"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  echo "Copy .env.example to .env.vps and fill values first." >&2
  exit 2
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 2
fi

cd "$DEPLOY_DIR"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build

wait_http() {
  local url="$1"
  local attempts="${2:-20}"
  local sleep_s="${3:-2}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_s"
  done
  return 1
}

echo "--- compose status ---"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo "--- smoke checks ---"
wait_http "http://127.0.0.1:18100/api/health" 30 2
curl -fsSI http://127.0.0.1:18101/ >/dev/null

echo "Deployment stack is up. Configure reverse-proxy route /agentic-mat next."
