from __future__ import annotations

import argparse
import json

from myMAT_app.api.thread_memory import create_thread_memory_store_from_env


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Initialize/check PostgreSQL + pgvector schema for myMAT thread memory "
            "using MYMAT_THREADS_* environment variables."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print health payload as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    store = create_thread_memory_store_from_env()
    health = store.health()

    if args.json:
        print(json.dumps(health, indent=2, ensure_ascii=False))
    else:
        print("=== Thread Memory Health ===")
        print(f"enabled: {health.get('enabled')}")
        print(f"ready: {health.get('ready')}")
        print(f"db_name: {health.get('db_name')}")
        print(f"vector_dims: {health.get('vector_dims')}")
        print(f"embedding_model: {health.get('embedding_model')}")
        if health.get("last_error"):
            print(f"last_error: {health.get('last_error')}")

    if not health.get("enabled", False):
        print("Thread memory is disabled. Set MYMAT_THREADS_ENABLED=1 to enable.")
        return 2
    return 0 if health.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
