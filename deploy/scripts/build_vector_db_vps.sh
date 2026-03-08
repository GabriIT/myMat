#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi
if [[ -f "$REPO_ROOT/deploy/.env.vps" ]]; then
  set -a
  source "$REPO_ROOT/deploy/.env.vps"
  set +a
fi

KNOWLEDGE_ROOT=""
ACTIVE_DB_PATH=""
COLLECTION="${MYMAT_COLLECTION:-myrag_docs_markdown}"
PYTHON_BIN=""
REPORT_DIR="/tmp/mymat_deploy_reports"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --knowledge-root)
      KNOWLEDGE_ROOT="$2"
      shift 2
      ;;
    --active-db-path)
      ACTIVE_DB_PATH="$2"
      shift 2
      ;;
    --collection)
      COLLECTION="$2"
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --report-dir)
      REPORT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      cat <<USAGE
Usage: build_vector_db_vps.sh --knowledge-root PATH --active-db-path PATH [options]
  --collection NAME      Chroma collection (default: MYMAT_COLLECTION or myrag_docs_markdown)
  --python-bin PATH      Python interpreter (default: .venv/bin/python then python3)
  --report-dir PATH      Directory for parser/ingest reports
USAGE
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$KNOWLEDGE_ROOT" || -z "$ACTIVE_DB_PATH" ]]; then
  echo "--knowledge-root and --active-db-path are required" >&2
  exit 2
fi

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

if [[ ! -x "$PYTHON_BIN" ]] && ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 2
fi

if [[ ! -d "$KNOWLEDGE_ROOT" ]]; then
  echo "Knowledge root does not exist: $KNOWLEDGE_ROOT" >&2
  exit 2
fi

mkdir -p "$REPORT_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
AUDIT_REPORT="$REPORT_DIR/parse_audit_${TIMESTAMP}.json"
UPGRADE_LOG="$REPORT_DIR/vector_upgrade_${TIMESTAMP}.log"
INSPECT_LOG="$REPORT_DIR/vector_inspect_${TIMESTAMP}.log"

cd "$REPO_ROOT"

echo "=== VPS Vector Build Stage (myMAT) ==="
echo "Repo root: $REPO_ROOT"
echo "Knowledge root: $KNOWLEDGE_ROOT"
echo "Active DB path: $ACTIVE_DB_PATH"
echo "Collection: $COLLECTION"
echo "Python: $PYTHON_BIN"

echo "[1/3] Strict parser audit"
"$PYTHON_BIN" -m myMAT_app.parser.audit \
  --knowledge-root "$KNOWLEDGE_ROOT" \
  --report-path "$AUDIT_REPORT" \
  --strict

echo "[2/3] Upgrade vector DB (strict parse + quiet parser warnings)"
"$PYTHON_BIN" -m myMAT_app.vector.upgrade_cli \
  --knowledge-root "$KNOWLEDGE_ROOT" \
  --active-db-path "$ACTIVE_DB_PATH" \
  --collection "$COLLECTION" \
  --strict-parse \
  --quiet-parser-warnings | tee "$UPGRADE_LOG"

echo "[3/3] Inspect active vector DB"
"$PYTHON_BIN" -m myMAT_app.vector.inspect_cli \
  --db-path "$ACTIVE_DB_PATH" \
  --collection "$COLLECTION" \
  --sample 3 | tee "$INSPECT_LOG"

vector_count=$(awk -F': ' '/Vector count/ {print $2; exit}' "$INSPECT_LOG")
if [[ -z "$vector_count" ]]; then
  echo "Failed to parse vector count from inspect output" >&2
  exit 1
fi
if [[ "$vector_count" -le 0 ]]; then
  echo "Vector count is zero after upgrade" >&2
  exit 1
fi

if [[ ! -f "$ACTIVE_DB_PATH/chroma.sqlite3" ]]; then
  echo "Missing expected file: $ACTIVE_DB_PATH/chroma.sqlite3" >&2
  exit 1
fi

echo "Vector build succeeded."
echo "Vector count: $vector_count"
echo "Audit report: $AUDIT_REPORT"
echo "Upgrade log: $UPGRADE_LOG"
echo "Inspect log: $INSPECT_LOG"
