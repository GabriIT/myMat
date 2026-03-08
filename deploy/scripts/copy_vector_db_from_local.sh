#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

LOCAL_DB_PATH="${MYMAT_DB_PATH:-$REPO_ROOT/vector_db}"
REMOTE_HOST=""
REMOTE_USER="$USER"
REMOTE_PORT="22"
REMOTE_DB_PATH=""
MODE="none"
REMOTE_REPO_PATH=""
REMOTE_PYTHON_BIN=".venv/bin/python"
COLLECTION="${MYMAT_COLLECTION:-myrag_docs_markdown}"
COMPOSE_PROJECT_DIR=""
COMPOSE_FILE="deploy/docker-compose.yml"
SYSTEMD_SERVICE="mymat-api"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote-host)
      REMOTE_HOST="$2"
      shift 2
      ;;
    --remote-user)
      REMOTE_USER="$2"
      shift 2
      ;;
    --remote-port)
      REMOTE_PORT="$2"
      shift 2
      ;;
    --local-db-path)
      LOCAL_DB_PATH="$2"
      shift 2
      ;;
    --remote-db-path)
      REMOTE_DB_PATH="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --remote-repo-path)
      REMOTE_REPO_PATH="$2"
      shift 2
      ;;
    --remote-python-bin)
      REMOTE_PYTHON_BIN="$2"
      shift 2
      ;;
    --collection)
      COLLECTION="$2"
      shift 2
      ;;
    --compose-project-dir)
      COMPOSE_PROJECT_DIR="$2"
      shift 2
      ;;
    --compose-file)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --systemd-service)
      SYSTEMD_SERVICE="$2"
      shift 2
      ;;
    -h|--help)
      cat <<USAGE
Usage: copy_vector_db_from_local.sh --remote-host HOST --remote-db-path PATH [options]
  --local-db-path PATH       Local vector_db path (default: MYMAT_DB_PATH from .env or repo vector_db)
  --remote-user USER         SSH user (default: current user)
  --remote-port PORT         SSH port (default: 22)
  --mode MODE                Restart mode: none|compose|systemd (default: none)
  --remote-repo-path PATH    If set, run remote inspect_cli after sync
  --remote-python-bin PATH   Remote python binary used for inspect_cli
  --collection NAME          Chroma collection for inspect
  --compose-project-dir PATH Remote compose project root
USAGE
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$REMOTE_HOST" || -z "$REMOTE_DB_PATH" ]]; then
  echo "--remote-host and --remote-db-path are required" >&2
  exit 2
fi

if [[ -z "$COMPOSE_PROJECT_DIR" ]]; then
  if [[ -n "$REMOTE_REPO_PATH" ]]; then
    COMPOSE_PROJECT_DIR="$REMOTE_REPO_PATH"
  else
    COMPOSE_PROJECT_DIR="/home/$REMOTE_USER/mymat-deploy/myMAT_app"
  fi
fi

if [[ ! -d "$LOCAL_DB_PATH" ]]; then
  echo "Local vector DB path does not exist: $LOCAL_DB_PATH" >&2
  exit 2
fi
if [[ ! -f "$LOCAL_DB_PATH/chroma.sqlite3" ]]; then
  echo "Local vector DB missing chroma.sqlite3: $LOCAL_DB_PATH" >&2
  exit 2
fi

SSH_TARGET="$REMOTE_USER@$REMOTE_HOST"
SSH_CMD=(ssh -p "$REMOTE_PORT" "$SSH_TARGET")
RSYNC_SSH="ssh -p $REMOTE_PORT"

stop_remote() {
  case "$MODE" in
    none)
      ;;
    compose)
      "${SSH_CMD[@]}" "cd '$COMPOSE_PROJECT_DIR' && docker compose -f '$COMPOSE_FILE' stop mymat-api"
      ;;
    systemd)
      "${SSH_CMD[@]}" "sudo systemctl stop '$SYSTEMD_SERVICE'"
      ;;
    *)
      echo "Unsupported mode: $MODE" >&2
      exit 2
      ;;
  esac
}

start_remote() {
  case "$MODE" in
    none)
      ;;
    compose)
      "${SSH_CMD[@]}" "cd '$COMPOSE_PROJECT_DIR' && docker compose -f '$COMPOSE_FILE' start mymat-api"
      ;;
    systemd)
      "${SSH_CMD[@]}" "sudo systemctl start '$SYSTEMD_SERVICE'"
      ;;
  esac
}

echo "Stopping remote API service (mode=$MODE)..."
stop_remote

echo "Creating remote vector DB directory..."
"${SSH_CMD[@]}" "mkdir -p '$REMOTE_DB_PATH'"

echo "Syncing local vector DB to VPS..."
rsync -az --delete -e "$RSYNC_SSH" "$LOCAL_DB_PATH/" "$SSH_TARGET:$REMOTE_DB_PATH/"

echo "Verifying remote vector DB files..."
"${SSH_CMD[@]}" "test -f '$REMOTE_DB_PATH/chroma.sqlite3'"
"${SSH_CMD[@]}" "find '$REMOTE_DB_PATH' -maxdepth 2 -type f | head -n 10"

echo "Starting remote API service (mode=$MODE)..."
start_remote

if [[ -n "$REMOTE_REPO_PATH" ]]; then
  echo "Running remote vector inspect..."
  "${SSH_CMD[@]}" "cd '$REMOTE_REPO_PATH' && '$REMOTE_PYTHON_BIN' -m myMAT_app.vector.inspect_cli --db-path '$REMOTE_DB_PATH' --collection '$COLLECTION' --sample 1"
fi

echo "Fallback vector DB copy completed successfully."
