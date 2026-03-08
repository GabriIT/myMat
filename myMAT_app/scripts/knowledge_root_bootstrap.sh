#!/usr/bin/env bash
set -euo pipefail

myrag_load_repo_env() {
  local root_dir="$1"
  if [[ -f "$root_dir/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$root_dir/.env"
    set +a
  fi
}

myrag_set_knowledge_roots() {
  local root_dir="$1"
  export MYRAG_RAW_KNOWLEDGE_ROOT="${MYRAG_RAW_KNOWLEDGE_ROOT:-$root_dir/myRAG_knowledge}"
  export MYRAG_KNOWLEDGE_ROOT="${MYRAG_KNOWLEDGE_ROOT:-$root_dir/myRAG_knowledge_index}"
  export MYRAG_KNOWLEDGE_INDEX_REPORT="${MYRAG_KNOWLEDGE_INDEX_REPORT:-/tmp/myrag_knowledge_index_report.json}"
  export MYRAG_SKIP_INDEX_REFRESH="${MYRAG_SKIP_INDEX_REFRESH:-0}"
}

myrag_refresh_indexed_knowledge() {
  local root_dir="$1"
  if [[ "${MYRAG_SKIP_INDEX_REFRESH}" == "1" ]]; then
    return 0
  fi
  if [[ ! -d "$MYRAG_RAW_KNOWLEDGE_ROOT" ]]; then
    echo "Raw knowledge root does not exist: $MYRAG_RAW_KNOWLEDGE_ROOT" >&2
    return 2
  fi
  echo "Refreshing indexed knowledge root: $MYRAG_KNOWLEDGE_ROOT"
  bash "$root_dir/myRAG_app/skills/knowledge-index-renamer/scripts/run_indexing.sh" \
    --input-root "$MYRAG_RAW_KNOWLEDGE_ROOT" \
    --output-root "$MYRAG_KNOWLEDGE_ROOT" \
    --report-path "$MYRAG_KNOWLEDGE_INDEX_REPORT" \
    --clean-output
}

myrag_enforce_or_inject_knowledge_root() {
  local python_bin="$1"
  shift
  local args=("$@")
  local has_knowledge_root=0
  local provided_knowledge_root=""

  for ((i = 0; i < ${#args[@]}; i++)); do
    if [[ "${args[$i]}" == "--knowledge-root" ]]; then
      has_knowledge_root=1
      if ((i + 1 >= ${#args[@]})); then
        echo "Missing value for --knowledge-root" >&2
        return 2
      fi
      provided_knowledge_root="${args[$((i + 1))]}"
      break
    elif [[ "${args[$i]}" == --knowledge-root=* ]]; then
      has_knowledge_root=1
      provided_knowledge_root="${args[$i]#--knowledge-root=}"
      break
    fi
  done

  MYRAG_KNOWLEDGE_EXTRA_ARGS=()
  if [[ $has_knowledge_root -eq 0 ]]; then
    MYRAG_KNOWLEDGE_EXTRA_ARGS=(--knowledge-root "$MYRAG_KNOWLEDGE_ROOT")
    return 0
  fi

  local resolved_provided
  resolved_provided="$(
    "$python_bin" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' \
      "$provided_knowledge_root"
  )"
  local resolved_index
  resolved_index="$(
    "$python_bin" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' \
      "$MYRAG_KNOWLEDGE_ROOT"
  )"

  if [[ "$resolved_provided" != "$resolved_index" ]]; then
    echo "This wrapper requires --knowledge-root to be the indexed root: $resolved_index" >&2
    echo "Remove --knowledge-root or set it to myRAG_knowledge_index." >&2
    return 2
  fi
  return 0
}
