#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
INSTALL_NODE20="auto"
INSTALL_POSTGRES="auto"
INSTALL_NGINX="auto"

usage() {
  cat <<'USAGE'
Usage: vps_bootstrap_ubuntu24.sh [options]

Options:
  --dry-run                 Print actions without executing package/runtime changes
  --install-node20 MODE     auto|yes|no (default: auto)
  --install-postgres MODE   auto|yes|no (default: auto)
  --install-nginx MODE      auto|yes|no (default: auto)
  -h, --help                Show this help

Behavior:
  1) Node:
     - Keep global node untouched if already >=20.
     - If missing or older, install user-scoped Node 20 via nvm (no global replacement).
  2) PostgreSQL:
     - Reuse if major >=15 exists.
     - If missing or older, install PostgreSQL 16 side-by-side.
  3) Nginx:
     - Install only if missing.
     - If another proxy is active (apache/caddy), keep nginx stopped/disabled.
USAGE
}

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $*"
    return 0
  fi
  eval "$@"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

node_major() {
  if ! has_cmd node; then
    echo 0
    return 0
  fi
  node -v | sed -E 's/^v([0-9]+).*/\1/' || echo 0
}

postgres_major() {
  if ! has_cmd psql; then
    echo 0
    return 0
  fi
  psql --version | awk '{print $3}' | cut -d. -f1
}

mode_ok() {
  [[ "$1" == "auto" || "$1" == "yes" || "$1" == "no" ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --install-node20)
      INSTALL_NODE20="$2"
      shift 2
      ;;
    --install-postgres)
      INSTALL_POSTGRES="$2"
      shift 2
      ;;
    --install-nginx)
      INSTALL_NGINX="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if ! mode_ok "$INSTALL_NODE20" || ! mode_ok "$INSTALL_POSTGRES" || ! mode_ok "$INSTALL_NGINX"; then
  echo "Install modes must be one of: auto|yes|no" >&2
  exit 2
fi

echo "=== myMAT VPS Bootstrap (Ubuntu 24.04) ==="
echo "User: $(id -un)"
echo "Host: $(hostname)"
echo "Dry run: $DRY_RUN"

if [[ "$DRY_RUN" -eq 0 ]]; then
  run_cmd "sudo apt-get update -y"
  run_cmd "sudo apt-get install -y curl ca-certificates gnupg lsb-release software-properties-common"
fi

echo "--- Detect active proxies ---"
ACTIVE_NGINX="$(systemctl is-active nginx 2>/dev/null || true)"
ACTIVE_APACHE="$(systemctl is-active apache2 2>/dev/null || true)"
ACTIVE_CADDY="$(systemctl is-active caddy 2>/dev/null || true)"
echo "nginx=$ACTIVE_NGINX apache2=$ACTIVE_APACHE caddy=$ACTIVE_CADDY"

echo "--- Node 20 check ---"
NODE_MAJOR="$(node_major)"
if [[ "$INSTALL_NODE20" == "no" ]]; then
  echo "Skipping Node setup (--install-node20=no)"
elif [[ "$INSTALL_NODE20" == "yes" || "$NODE_MAJOR" -lt 20 ]]; then
  if [[ "$NODE_MAJOR" -ge 20 ]]; then
    echo "Node already >=20 (v$NODE_MAJOR)."
  else
    echo "Installing user-scoped Node 20 via nvm (current major=$NODE_MAJOR)."
    NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
      run_cmd "curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash"
    fi
    # shellcheck disable=SC1090
    source "$NVM_DIR/nvm.sh"
    run_cmd "nvm install 20"
    run_cmd "nvm alias default 20"
    run_cmd "nvm use 20"
    echo "Node via nvm: $(node -v)"
    echo "npm via nvm: $(npm -v)"
  fi
else
  echo "Node >=20 detected (v$NODE_MAJOR), no action."
fi

echo "--- PostgreSQL 15+ check ---"
PG_MAJOR="$(postgres_major)"
if [[ "$INSTALL_POSTGRES" == "no" ]]; then
  echo "Skipping PostgreSQL setup (--install-postgres=no)"
elif [[ "$INSTALL_POSTGRES" == "yes" || "$PG_MAJOR" -lt 15 ]]; then
  if [[ "$PG_MAJOR" -ge 15 ]]; then
    echo "PostgreSQL already >=15 (v$PG_MAJOR)."
  else
    echo "Installing PostgreSQL 16 side-by-side (current major=$PG_MAJOR)."
    run_cmd "sudo apt-get install -y postgresql-16 postgresql-client-16"
    run_cmd "sudo systemctl enable --now postgresql"
  fi
else
  echo "PostgreSQL >=15 detected (v$PG_MAJOR), no action."
fi

echo "--- Nginx check ---"
if [[ "$INSTALL_NGINX" == "no" ]]; then
  echo "Skipping Nginx setup (--install-nginx=no)"
elif [[ "$INSTALL_NGINX" == "yes" ]] || ! has_cmd nginx; then
  if has_cmd nginx; then
    echo "Nginx already installed: $(nginx -v 2>&1)"
  else
    echo "Installing Nginx."
    run_cmd "sudo apt-get install -y nginx"
  fi

  if [[ "$ACTIVE_APACHE" == "active" || "$ACTIVE_CADDY" == "active" ]]; then
    echo "Another proxy is active; keeping nginx stopped/disabled to avoid conflicts."
    run_cmd "sudo systemctl stop nginx || true"
    run_cmd "sudo systemctl disable nginx || true"
  fi
else
  echo "Nginx already installed, no action."
fi

echo "--- Result summary ---"
has_cmd node && echo "node: $(node -v)" || echo "node: missing"
has_cmd npm && echo "npm: $(npm -v)" || echo "npm: missing"
has_cmd psql && echo "psql: $(psql --version)" || echo "psql: missing"
has_cmd nginx && echo "nginx: $(nginx -v 2>&1)" || echo "nginx: missing"
echo "Bootstrap completed."
