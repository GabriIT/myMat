from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .export_chunks import _chunk_id
from .export_markdown import MarkdownExportConfig, _render_folder_markdown
from .parser_config import ParseConfig
from .parser_types import FileParseResult
from .parsers import parse_knowledge_base

DEFAULT_STATE_PATH = Path("myMAT_app/.state/incremental_source_manifest.json")
DEFAULT_MARKDOWN_OUTPUT_DIR = Path("myMAT_app/markdown_knowledge_incremental")
DEFAULT_CHUNKS_OUTPUT_PATH = Path("/tmp/myrag_chunks_incremental.jsonl")
DEFAULT_REPORT_PATH = Path("/tmp/myrag_incremental_pipeline_report.json")
DEFAULT_PROBE_DIR = Path("/tmp/myrag_pptx_probe_reports")


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def _load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        files = payload.get("files", {})
        if isinstance(files, dict):
            return {str(k): str(v) for k, v in files.items()}
    except Exception:
        return {}
    return {}


def _save_state(path: Path, files: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "files": dict(sorted(files.items(), key=lambda item: item[0].casefold())),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_slug(path: Path) -> str:
    stem = path.name
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in stem)


def _probe_with_skill_wrapper(
    *,
    repo_root: Path,
    input_path: Path,
    report_path: Path,
) -> tuple[bool, str]:
    cmd = [
        "bash",
        str(repo_root / "myMAT_app/skills/pptx-rag-parser/scripts/run_pptx_probe.sh"),
        "--pptx-path",
        str(input_path),
        "--report-path",
        str(report_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    ok = proc.returncode == 0
    message = (proc.stdout + "\n" + proc.stderr).strip()
    return ok, message


def _convert_ppt_to_pptx(ppt_path: Path, tmpdir: Path) -> Path:
    proc = subprocess.run(
        [
            "libreoffice",
            "--headless",
            "--convert-to",
            "pptx",
            "--outdir",
            str(tmpdir),
            str(ppt_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "libreoffice conversion failed")
    out = tmpdir / f"{ppt_path.stem}.pptx"
    if not out.exists():
        raise RuntimeError(f"Converted pptx not found: {out}")
    return out


def _run_markdown_export_for_subset(
    *,
    docs,
    results: list[FileParseResult],
    knowledge_root: Path,
    output_dir: Path,
) -> dict:
    config = MarkdownExportConfig(
        knowledge_root=knowledge_root,
        output_dir=output_dir,
        include_all_subfolders=False,
    )
    docs_by_folder: dict[str, list] = defaultdict(list)
    for doc in docs:
        folder_name = str((doc.metadata or {}).get("doc_type", "__unknown__"))
        docs_by_folder[folder_name].append(doc)

    failed_by_folder: dict[str, list[FileParseResult]] = defaultdict(list)
    for result in results:
        if result.status == "failed":
            try:
                rel = Path(result.source_path).resolve().relative_to(knowledge_root)
                folder_name = rel.parts[0] if len(rel.parts) > 1 else "__root__"
            except Exception:
                folder_name = "__external__"
            failed_by_folder[folder_name].append(result)

    folders = sorted(set(docs_by_folder.keys()) | set(failed_by_folder.keys()), key=str.casefold)
    output_dir.mkdir(parents=True, exist_ok=True)

    folder_summaries = []
    for folder_name in folders:
        markdown, sources_count, segments_count, char_count = _render_folder_markdown(
            folder_name=folder_name,
            docs=docs_by_folder.get(folder_name, []),
            failed_results=failed_by_folder.get(folder_name, []),
            config=config,
        )
        md_path = output_dir / f"{folder_name}.md"
        md_path.write_text(markdown, encoding="utf-8")
        folder_summaries.append(
            {
                "folder_name": folder_name,
                "markdown_path": str(md_path),
                "sources_count": sources_count,
                "segments_count": segments_count,
                "char_count": char_count,
                "failures_count": len(failed_by_folder.get(folder_name, [])),
            }
        )
    return {
        "folders_written": len(folder_summaries),
        "folders": folder_summaries,
    }


def _write_chunks(*, docs, output_path: Path, chunk_size: int, chunk_overlap: int) -> dict:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(docs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for idx, chunk in enumerate(chunks):
            metadata = dict(chunk.metadata)
            record = {
                "id": _chunk_id(metadata, idx),
                "text": chunk.page_content,
                "metadata": {
                    **metadata,
                    "chunk_index": idx,
                    "char_count": len(chunk.page_content),
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"chunks_written": len(chunks), "output_path": str(output_path)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Incremental source->markdown->chunks pipeline. "
            "Processes only newly added files by default."
        )
    )
    parser.add_argument("--knowledge-root", required=True, help="Knowledge root directory.")
    parser.add_argument(
        "--markdown-output-dir",
        default=str(DEFAULT_MARKDOWN_OUTPUT_DIR),
        help=f"Output dir for incremental markdown snapshots (default: {DEFAULT_MARKDOWN_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--chunks-output-path",
        default=str(DEFAULT_CHUNKS_OUTPUT_PATH),
        help=f"Output JSONL path for incremental chunks (default: {DEFAULT_CHUNKS_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--state-path",
        default=str(DEFAULT_STATE_PATH),
        help=f"State file to track processed files (default: {DEFAULT_STATE_PATH}).",
    )
    parser.add_argument(
        "--probe-report-dir",
        default=str(DEFAULT_PROBE_DIR),
        help=f"Directory for per-file PPTX probe reports (default: {DEFAULT_PROBE_DIR}).",
    )
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Pipeline summary report path (default: {DEFAULT_REPORT_PATH}).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Chunk size for split (default: 1000).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Chunk overlap for split (default: 200).",
    )
    parser.add_argument(
        "--include-modified",
        action="store_true",
        help="Also process modified files (default is only newly added files).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit code 1 when parse failures or unsupported new .ppt files are detected.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    knowledge_root = Path(args.knowledge_root).expanduser().resolve()
    markdown_output_dir = Path(args.markdown_output_dir).expanduser().resolve()
    chunks_output_path = Path(args.chunks_output_path).expanduser().resolve()
    state_path = Path(args.state_path).expanduser().resolve()
    probe_report_dir = Path(args.probe_report_dir).expanduser().resolve()
    report_path = Path(args.report_path).expanduser().resolve()

    if not knowledge_root.exists() or not knowledge_root.is_dir():
        print(f"Validation error: knowledge root is invalid: {knowledge_root}")
        return 2

    repo_root = Path(__file__).resolve().parents[2]
    parse_exts = set(ParseConfig(knowledge_root=knowledge_root).supported_extensions)
    tracked_exts = set(parse_exts) | {".ppt"}

    old_state = _load_state(state_path)
    all_files = sorted(
        path
        for path in knowledge_root.rglob("*")
        if path.is_file() and path.suffix.lower() in tracked_exts
    )
    current_state = {str(path): _fingerprint(path) for path in all_files}

    new_files = [path for path in all_files if str(path) not in old_state]
    modified_files = [
        path
        for path in all_files
        if str(path) in old_state and old_state[str(path)] != current_state[str(path)]
    ]
    removed_files = sorted(set(old_state.keys()) - set(current_state.keys()))

    selected = list(new_files)
    if args.include_modified:
        selected.extend(modified_files)
    selected = sorted(set(selected))

    probe_report_dir.mkdir(parents=True, exist_ok=True)
    probe_results = []
    unsupported_ppt = [path for path in selected if path.suffix.lower() == ".ppt"]
    pptx_targets = [path for path in selected if path.suffix.lower() == ".pptx"]

    for pptx_path in pptx_targets:
        probe_path = probe_report_dir / f"{_safe_slug(pptx_path)}.json"
        ok, output = _probe_with_skill_wrapper(
            repo_root=repo_root, input_path=pptx_path, report_path=probe_path
        )
        probe_results.append(
            {
                "source_path": str(pptx_path),
                "report_path": str(probe_path),
                "ok": ok,
                "output_excerpt": output[:2000],
            }
        )

    for ppt_path in unsupported_ppt:
        with tempfile.TemporaryDirectory(prefix="myrag_ppt_convert_") as tmp:
            tmpdir = Path(tmp)
            probe_payload = {
                "source_path": str(ppt_path),
                "ok": False,
                "report_path": None,
                "output_excerpt": "PPT files are not directly supported; convert to .pptx first.",
            }
            try:
                converted = _convert_ppt_to_pptx(ppt_path, tmpdir)
                probe_path = probe_report_dir / f"{_safe_slug(ppt_path)}.json"
                ok, output = _probe_with_skill_wrapper(
                    repo_root=repo_root,
                    input_path=converted,
                    report_path=probe_path,
                )
                probe_payload.update(
                    {
                        "ok": ok,
                        "report_path": str(probe_path),
                        "output_excerpt": output[:2000],
                    }
                )
            except Exception as exc:
                probe_payload["output_excerpt"] = f"PPT conversion/probe failed: {exc}"
            probe_results.append(probe_payload)

    parse_targets = [path for path in selected if path.suffix.lower() in parse_exts]
    parse_results: list[FileParseResult] = []
    docs = []
    if parse_targets:
        config = ParseConfig(knowledge_root=knowledge_root, include_paths=parse_targets)
        docs, parse_results = parse_knowledge_base(config)

    markdown_summary = _run_markdown_export_for_subset(
        docs=docs,
        results=parse_results,
        knowledge_root=knowledge_root,
        output_dir=markdown_output_dir,
    )
    chunk_summary = _write_chunks(
        docs=docs,
        output_path=chunks_output_path,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    new_state = dict(old_state)
    for removed in removed_files:
        new_state.pop(removed, None)
    successful_paths = {
        result.source_path
        for result in parse_results
        if result.status in {"success", "warning"}
    }
    for path in selected:
        path_key = str(path)
        if path.suffix.lower() in parse_exts:
            if path_key in successful_paths:
                new_state[path_key] = current_state[path_key]
            continue
        if path.suffix.lower() == ".ppt":
            continue
        new_state[path_key] = current_state[path_key]
    _save_state(state_path, new_state)

    failed_count = sum(1 for result in parse_results if result.status == "failed")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "knowledge_root": str(knowledge_root),
        "state_path": str(state_path),
        "selection": {
            "new_files_count": len(new_files),
            "modified_files_count": len(modified_files),
            "removed_files_count": len(removed_files),
            "selected_files_count": len(selected),
            "selected_files": [str(path) for path in selected],
        },
        "probe": {
            "reports_count": len(probe_results),
            "results": probe_results,
        },
        "parse": {
            "targets_count": len(parse_targets),
            "documents_count": len(docs),
            "failed_count": failed_count,
            "results": [result.to_dict() for result in parse_results],
        },
        "markdown": markdown_summary,
        "chunks": chunk_summary,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== Incremental Source Pipeline Summary ===")
    print(f"Knowledge root: {knowledge_root}")
    print(f"New files: {len(new_files)}")
    print(f"Modified files: {len(modified_files)} (include={args.include_modified})")
    print(f"Selected files: {len(selected)}")
    print(f"PPT/PPTX probes run: {len(probe_results)}")
    print(f"Parsed documents: {len(docs)}")
    print(f"Parse failures: {failed_count}")
    print(f"Markdown output dir: {markdown_output_dir}")
    print(f"Chunks output: {chunks_output_path}")
    print(f"State updated: {state_path}")
    print(f"Report: {report_path}")

    if not selected:
        print("No new files detected. Nothing to process.")
        return 0

    if args.strict and (failed_count > 0 or len(unsupported_ppt) > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
