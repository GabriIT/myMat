#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DB="${1:-/home/gabri/udemy/llm_engineering/myRAG_app/vector_db_markdown}"
TARGET_DB="${2:-$ROOT_DIR/vector_db}"

if [[ ! -d "$SOURCE_DB" ]]; then
  echo "Source vector store not found: $SOURCE_DB" >&2
  exit 2
fi

mkdir -p "$TARGET_DB"
rsync -a --delete "$SOURCE_DB"/ "$TARGET_DB"/

echo "Synced vector store"
echo "source=$SOURCE_DB"
echo "target=$TARGET_DB"
