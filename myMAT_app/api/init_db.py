from __future__ import annotations

import argparse
import json

from myMAT_app.api.db.ops_store import create_ops_store_from_env
from myMAT_app.api.thread_memory import create_thread_memory_store_from_env


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize myMAT PostgreSQL schemas (ops + thread memory).")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--seed", action="store_true", help="Also seed deterministic mock data.")
    parser.add_argument("--reset", action="store_true", help="Reset catalog/orders before seeding.")
    parser.add_argument("--seed-value", type=int, default=42, help="Deterministic seed value.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    thread_store = create_thread_memory_store_from_env()
    ops_store = create_ops_store_from_env()

    thread_health = thread_store.health()
    ops_health = ops_store.health()

    output: dict[str, object] = {
        "thread_memory": thread_health,
        "ops": ops_health,
    }

    if args.seed and bool(ops_health.get("ready", False)):
        counts = ops_store.seed_mock_data(reset=args.reset, seed=args.seed_value)
        output["seed"] = counts

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        print("=== myMAT DB Init ===")
        print(f"thread_memory.enabled={thread_health.get('enabled')} ready={thread_health.get('ready')}")
        print(f"ops.enabled={ops_health.get('enabled')} ready={ops_health.get('ready')}")
        if thread_health.get("last_error"):
            print(f"thread_memory.error={thread_health.get('last_error')}")
        if ops_health.get("last_error"):
            print(f"ops.error={ops_health.get('last_error')}")
        if "seed" in output:
            print(f"seed.counts={output['seed']}")

    if not bool(ops_health.get("ready", False)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
