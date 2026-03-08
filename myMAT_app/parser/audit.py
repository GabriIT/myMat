from __future__ import annotations

import argparse
from pathlib import Path

from .parser_config import ParseConfig
from .parsers import parse_knowledge_base
from .reporting import print_parse_summary, write_parse_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse a knowledge folder and produce a structured parser audit report."
    )
    parser.add_argument(
        "--knowledge-root",
        required=True,
        help="Path to the root knowledge folder (recursively parsed).",
    )
    parser.add_argument(
        "--report-path",
        required=True,
        help="Path to the JSON report output file.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any file parsing fails.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = ParseConfig(knowledge_root=Path(args.knowledge_root), strict_mode=args.strict)

    try:
        _, results = parse_knowledge_base(config)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"Validation error: {exc}")
        return 2

    print_parse_summary(results)
    write_parse_report(results, Path(args.report_path))
    print(f"\nReport written to: {args.report_path}")

    has_failures = any(result.status == "failed" for result in results)
    if config.strict_mode and has_failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

