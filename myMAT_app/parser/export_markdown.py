from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from langchain_core.documents import Document

from .parser_config import ParseConfig
from .parser_types import FileParseResult
from .parsers import parse_knowledge_base

GroupingMode = Literal["source"]
DEFAULT_REPORT_PATH = Path("/tmp/myrag_markdown_export_report.json")


@dataclass(slots=True)
class MarkdownExportConfig:
    knowledge_root: Path
    output_dir: Path = Path("myMAT_app/markdown_knowledge")
    strict: bool = False
    include_all_subfolders: bool = True
    include_failure_section: bool = True
    grouping_mode: GroupingMode = "source"

    def __post_init__(self) -> None:
        self.knowledge_root = Path(self.knowledge_root).expanduser().resolve()
        self.output_dir = Path(self.output_dir).expanduser().resolve()
        if self.grouping_mode != "source":
            raise ValueError(f"Unsupported grouping_mode: {self.grouping_mode}")


@dataclass(slots=True)
class FolderMarkdownResult:
    folder_name: str
    markdown_path: str
    sources_count: int
    segments_count: int
    char_count: int
    failures_count: int

    def to_dict(self) -> dict:
        return {
            "folder_name": self.folder_name,
            "markdown_path": self.markdown_path,
            "sources_count": self.sources_count,
            "segments_count": self.segments_count,
            "char_count": self.char_count,
            "failures_count": self.failures_count,
        }


@dataclass(slots=True)
class ExportMarkdownRunResult:
    folders: list[FolderMarkdownResult]
    total_markdown_files: int
    total_sources: int
    total_segments: int
    total_failures: int

    def to_dict(self) -> dict:
        return {
            "folders": [folder.to_dict() for folder in self.folders],
            "total_markdown_files": self.total_markdown_files,
            "total_sources": self.total_sources,
            "total_segments": self.total_segments,
            "total_failures": self.total_failures,
        }


def _discover_top_level_folders(knowledge_root: Path) -> list[str]:
    return sorted(path.name for path in knowledge_root.iterdir() if path.is_dir())


def _folder_from_source_path(knowledge_root: Path, source_path: str) -> str:
    source = Path(source_path)
    try:
        relative = source.relative_to(knowledge_root)
    except ValueError:
        return "__external__"
    if not relative.parts:
        return "__root__"
    if len(relative.parts) == 1:
        return "__root__"
    return relative.parts[0]


def _source_sort_key(source_path: str) -> tuple[str, str]:
    path = Path(source_path)
    return (str(path.parent).casefold(), path.name.casefold())


def _segment_sort_key(indexed_doc: tuple[int, Document]) -> tuple[int, str, int]:
    original_index, doc = indexed_doc
    metadata = doc.metadata or {}
    page_number = metadata.get("page_number")
    if isinstance(page_number, int):
        page_rank = page_number
    else:
        page_rank = 10**9

    sheet_name = metadata.get("sheet_name")
    if isinstance(sheet_name, str):
        sheet_rank = sheet_name.casefold()
    else:
        sheet_rank = ""
    return (page_rank, sheet_rank, original_index)


def _render_folder_markdown(
    *,
    folder_name: str,
    docs: list[Document],
    failed_results: list[FileParseResult],
    config: MarkdownExportConfig,
) -> tuple[str, int, int, int]:
    docs_by_source: dict[str, list[Document]] = defaultdict(list)
    for doc in docs:
        source_path = str(doc.metadata.get("source", ""))
        docs_by_source[source_path].append(doc)

    sources_count = len(docs_by_source)
    segments_count = len(docs)
    char_count = sum(len(doc.page_content or "") for doc in docs)

    lines: list[str] = []
    lines.append(f"# {folder_name}")
    lines.append("")
    lines.append(f"- generated_at: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- knowledge_root: {config.knowledge_root}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- sources: {sources_count}")
    lines.append(f"- segments: {segments_count}")
    lines.append(f"- characters: {char_count}")
    lines.append(f"- failed_files: {len(failed_results)}")
    lines.append("")

    if not docs:
        lines.append("No parsed content found for this folder.")
        lines.append("")
    else:
        for source_path in sorted(docs_by_source, key=_source_sort_key):
            source_docs = docs_by_source[source_path]
            first_meta = source_docs[0].metadata or {}
            source_name = str(first_meta.get("source_name") or Path(source_path).name)

            lines.append(f"## Source: {source_name}")
            lines.append(f"- source_path: {source_path}")
            lines.append(f"- source_ext: {first_meta.get('source_ext', '-')}")
            lines.append(f"- parser_used: {first_meta.get('parser_used', '-')}")
            lines.append(f"- fallback_used: {first_meta.get('fallback_used', '-')}")
            lines.append(f"- parse_status: {first_meta.get('parse_status', '-')}")
            lines.append(f"- extracted_chars: {first_meta.get('extracted_chars', '-')}")
            lines.append("")

            for segment_index, (_, doc) in enumerate(
                sorted(enumerate(source_docs), key=_segment_sort_key),
                start=1,
            ):
                metadata = doc.metadata or {}
                labels: list[str] = []
                if metadata.get("page_number") is not None:
                    labels.append(f"page {metadata.get('page_number')}")
                if metadata.get("sheet_name") is not None:
                    labels.append(f"sheet {metadata.get('sheet_name')}")
                suffix = f" ({' | '.join(labels)})" if labels else ""
                lines.append(f"### Segment {segment_index}{suffix}")
                lines.append("")
                content = (doc.page_content or "").strip()
                lines.append(content if content else "[empty segment]")
                lines.append("")

    if config.include_failure_section:
        lines.append("## Parse Failures")
        lines.append("")
        if not failed_results:
            lines.append("No failed files for this folder.")
            lines.append("")
        else:
            for result in sorted(failed_results, key=lambda item: item.source_path.casefold()):
                source_name = Path(result.source_path).name
                lines.append(f"### {source_name}")
                lines.append(f"- source_path: {result.source_path}")
                lines.append(f"- extension: {result.extension}")
                lines.append(f"- parser_used: {result.parser_used}")
                lines.append(f"- fallback_used: {result.fallback_used}")
                lines.append("")
                if result.issues:
                    lines.append("Issues:")
                    for issue in result.issues:
                        lines.append(f"- [{issue.code}] {issue.message}")
                        lines.append(f"- suggested_action: {issue.suggested_action}")
                else:
                    lines.append("Issues:")
                    lines.append("- No issue metadata captured.")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n", sources_count, segments_count, char_count


def export_folder_markdown(
    config: MarkdownExportConfig,
) -> tuple[ExportMarkdownRunResult, list[FileParseResult]]:
    if not config.knowledge_root.exists():
        raise FileNotFoundError(f"Knowledge root does not exist: {config.knowledge_root}")
    if not config.knowledge_root.is_dir():
        raise NotADirectoryError(f"Knowledge root is not a directory: {config.knowledge_root}")

    parse_config = ParseConfig(knowledge_root=config.knowledge_root, strict_mode=config.strict)
    documents, parse_results = parse_knowledge_base(parse_config)

    docs_by_folder: dict[str, list[Document]] = defaultdict(list)
    for doc in documents:
        folder_name = str((doc.metadata or {}).get("doc_type", "__unknown__"))
        docs_by_folder[folder_name].append(doc)

    failed_by_folder: dict[str, list[FileParseResult]] = defaultdict(list)
    for result in parse_results:
        if result.status == "failed":
            folder_name = _folder_from_source_path(config.knowledge_root, result.source_path)
            failed_by_folder[folder_name].append(result)

    folder_names: set[str] = set()
    if config.include_all_subfolders:
        folder_names.update(_discover_top_level_folders(config.knowledge_root))
    folder_names.update(docs_by_folder.keys())
    folder_names.update(failed_by_folder.keys())

    config.output_dir.mkdir(parents=True, exist_ok=True)
    folder_results: list[FolderMarkdownResult] = []

    for folder_name in sorted(folder_names, key=str.casefold):
        folder_docs = docs_by_folder.get(folder_name, [])
        folder_failures = failed_by_folder.get(folder_name, [])

        markdown, sources_count, segments_count, char_count = _render_folder_markdown(
            folder_name=folder_name,
            docs=folder_docs,
            failed_results=folder_failures,
            config=config,
        )

        output_path = config.output_dir / f"{folder_name}.md"
        output_path.write_text(markdown, encoding="utf-8")
        folder_results.append(
            FolderMarkdownResult(
                folder_name=folder_name,
                markdown_path=str(output_path),
                sources_count=sources_count,
                segments_count=segments_count,
                char_count=char_count,
                failures_count=len(folder_failures),
            )
        )

    run_result = ExportMarkdownRunResult(
        folders=folder_results,
        total_markdown_files=len(folder_results),
        total_sources=sum(folder.sources_count for folder in folder_results),
        total_segments=sum(folder.segments_count for folder in folder_results),
        total_failures=sum(folder.failures_count for folder in folder_results),
    )
    return run_result, parse_results


def build_markdown_export_report(
    run_result: ExportMarkdownRunResult,
    parse_results: list[FileParseResult],
    config: MarkdownExportConfig,
) -> dict:
    failed_files = []
    for result in parse_results:
        if result.status != "failed":
            continue
        failed_files.append(
            {
                "folder_name": _folder_from_source_path(config.knowledge_root, result.source_path),
                "source_path": result.source_path,
                "extension": result.extension,
                "status": result.status,
                "parser_used": result.parser_used,
                "fallback_used": result.fallback_used,
                "extracted_chars": result.extracted_chars,
                "documents_count": result.documents_count,
                "issues": [issue.to_dict() for issue in result.issues],
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "knowledge_root": str(config.knowledge_root),
        "output_dir": str(config.output_dir),
        "summary": {
            "total_markdown_files": run_result.total_markdown_files,
            "total_sources": run_result.total_sources,
            "total_segments": run_result.total_segments,
            "total_failures": run_result.total_failures,
        },
        "folders": [folder.to_dict() for folder in run_result.folders],
        "failed_files": failed_files,
    }


def write_markdown_export_report(
    run_result: ExportMarkdownRunResult,
    parse_results: list[FileParseResult],
    config: MarkdownExportConfig,
    report_path: Path,
) -> None:
    report = build_markdown_export_report(run_result, parse_results, config)
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def print_markdown_export_summary(run_result: ExportMarkdownRunResult) -> None:
    print("=== Markdown Export Summary ===")
    print(f"Markdown files written: {run_result.total_markdown_files}")
    print(f"Total sources: {run_result.total_sources}")
    print(f"Total segments: {run_result.total_segments}")
    print(f"Total failed files: {run_result.total_failures}")
    print("")
    print("Per-folder results:")
    for folder in run_result.folders:
        print(
            f"  {folder.folder_name}: md={folder.markdown_path} "
            f"sources={folder.sources_count} segments={folder.segments_count} "
            f"chars={folder.char_count} failures={folder.failures_count}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a knowledge base and export one markdown file per top-level "
            "knowledge folder, grouped by source."
        )
    )
    parser.add_argument(
        "--knowledge-root",
        required=True,
        help="Path to the knowledge root folder.",
    )
    parser.add_argument(
        "--output-dir",
        default="myMAT_app/markdown_knowledge",
        help="Output directory where folder-level markdown files are written.",
    )
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to JSON export report output.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any file parse failed.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = MarkdownExportConfig(
        knowledge_root=Path(args.knowledge_root),
        output_dir=Path(args.output_dir),
        strict=args.strict,
    )

    try:
        run_result, parse_results = export_folder_markdown(config)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"Validation error: {exc}")
        return 2

    print_markdown_export_summary(run_result)

    if args.report_path:
        report_path = Path(args.report_path)
        write_markdown_export_report(run_result, parse_results, config, report_path)
        print(f"\nReport written to: {report_path}")

    if config.strict and run_result.total_failures > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
