from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .parser_types import FileParseResult


def build_parse_report(results: list[FileParseResult]) -> dict:
    extension_counts = Counter(result.extension for result in results)
    status_counts = Counter(result.status for result in results)
    issue_code_counts = Counter(
        issue.code for result in results for issue in result.issues
    )
    total_documents = sum(result.documents_count for result in results)

    summary = {
        "total_files": len(results),
        "total_documents": total_documents,
        "extensions": dict(sorted(extension_counts.items())),
        "statuses": dict(sorted(status_counts.items())),
        "issue_codes": dict(sorted(issue_code_counts.items())),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "files": [result.to_dict() for result in results],
    }


def write_parse_report(results: list[FileParseResult], output_path: Path) -> None:
    report = build_parse_report(results)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def print_parse_summary(results: list[FileParseResult]) -> None:
    report = build_parse_report(results)
    summary = report["summary"]
    print("=== Parser Audit Summary ===")
    print(f"Total files: {summary['total_files']}")
    print(f"Total documents emitted: {summary['total_documents']}")
    print("")
    print("Status counts:")
    for status, count in summary["statuses"].items():
        print(f"  {status:>7}: {count}")
    print("Extension counts:")
    for ext, count in summary["extensions"].items():
        print(f"  {ext:>7}: {count}")
    print("")
    print("File results:")
    for result in results:
        issue_codes = ", ".join(issue.code for issue in result.issues) or "-"
        print(
            f"  [{result.status.upper():7}] {result.source_path} | "
            f"chars={result.extracted_chars} docs={result.documents_count} "
            f"parser={result.parser_used} fallback={result.fallback_used} issues={issue_codes}"
        )

