#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from myMAT_app.api.db.ops_store import create_ops_store_from_env


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed deterministic mock data for myMAT_ops.")
    parser.add_argument("--reset", action="store_true", help="Reset catalog/orders before seeding.")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    store = create_ops_store_from_env()
    health = store.health()
    if not health.get("enabled", False):
        print("myMAT ops DB is disabled. Set MYMAT_OPS_ENABLED=1.")
        return 2
    if not health.get("ready", False):
        print(f"myMAT ops DB is not ready: {health.get('last_error')}")
        return 1

    counts = store.seed_mock_data(reset=args.reset, seed=args.seed)
    payload = {"counts": counts, "db": health.get("db_name")}

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("Seed completed")
        print(f"customers={counts['customers']} materials={counts['materials']} orders={counts['orders']}")

    if counts["customers"] < 10 or counts["materials"] < 40 or counts["orders"] < 30:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
