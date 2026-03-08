#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

ACTIVE_DB_PATH="${MYMAT_DB_PATH:-$REPO_ROOT/vector_db}"
BACKUP_ROOT=""
BACKUP_NAME=""
DRY_RUN=0

usage() {
  cat <<USAGE
Usage: rollback_vector_db.sh [options]

Options:
  --active-db-path PATH   Active vector DB path to restore
  --backup-root PATH      Backup root folder (default: <active_parent>/<active_db_name>_backups)
  --backup-name NAME      Specific backup folder name to restore
  --dry-run               Print planned actions without changing files
  -h, --help              Show this help message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --active-db-path)
      ACTIVE_DB_PATH="$2"
      shift 2
      ;;
    --backup-root)
      BACKUP_ROOT="$2"
      shift 2
      ;;
    --backup-name)
      BACKUP_NAME="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
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

ACTIVE_DB_PATH="$(python3 - <<PY
from pathlib import Path
print(Path("$ACTIVE_DB_PATH").expanduser().resolve())
PY
)"
ACTIVE_PARENT="$(dirname "$ACTIVE_DB_PATH")"
ACTIVE_NAME="$(basename "$ACTIVE_DB_PATH")"

if [[ -z "$BACKUP_ROOT" ]]; then
  BACKUP_ROOT="$ACTIVE_PARENT/${ACTIVE_NAME}_backups"
fi
BACKUP_ROOT="$(python3 - <<PY
from pathlib import Path
print(Path("$BACKUP_ROOT").expanduser().resolve())
PY
)"

if [[ ! -d "$BACKUP_ROOT" ]]; then
  echo "Backup root does not exist: $BACKUP_ROOT" >&2
  exit 2
fi

if [[ -n "$BACKUP_NAME" ]]; then
  SELECTED_BACKUP="$BACKUP_ROOT/$BACKUP_NAME"
  if [[ ! -d "$SELECTED_BACKUP" ]]; then
    echo "Requested backup not found: $SELECTED_BACKUP" >&2
    exit 2
  fi
else
  SELECTED_BACKUP="$(python3 - <<PY
from pathlib import Path
root = Path("$BACKUP_ROOT")
dirs = [p for p in root.iterdir() if p.is_dir()]
print(max(dirs, key=lambda p: p.stat().st_mtime) if dirs else "")
PY
)"
  if [[ -z "$SELECTED_BACKUP" ]]; then
    echo "No backup folders found in: $BACKUP_ROOT" >&2
    exit 2
  fi
fi

if [[ ! -f "$SELECTED_BACKUP/chroma.sqlite3" ]]; then
  echo "Selected backup is not a valid Chroma DB: $SELECTED_BACKUP" >&2
  exit 2
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
PRE_ROLLBACK_ARCHIVE="$BACKUP_ROOT/${ACTIVE_NAME}_rollback_pre_${STAMP}"

echo "=== Vector DB Rollback Plan ==="
echo "Active DB path: $ACTIVE_DB_PATH"
echo "Backup root: $BACKUP_ROOT"
echo "Selected backup: $SELECTED_BACKUP"
echo "Pre-rollback archive path: $PRE_ROLLBACK_ARCHIVE"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry-run enabled. No filesystem changes made."
  exit 0
fi

if [[ -e "$ACTIVE_DB_PATH" ]]; then
  mv "$ACTIVE_DB_PATH" "$PRE_ROLLBACK_ARCHIVE"
  echo "Archived current active DB to: $PRE_ROLLBACK_ARCHIVE"
fi

if ! mv "$SELECTED_BACKUP" "$ACTIVE_DB_PATH"; then
  echo "Rollback promotion failed." >&2
  if [[ -d "$PRE_ROLLBACK_ARCHIVE" && ! -e "$ACTIVE_DB_PATH" ]]; then
    mv "$PRE_ROLLBACK_ARCHIVE" "$ACTIVE_DB_PATH"
    echo "Restored previous active DB from pre-rollback archive."
  fi
  exit 1
fi

echo "Rollback complete. Active DB restored from backup."
echo "Current active DB: $ACTIVE_DB_PATH"
