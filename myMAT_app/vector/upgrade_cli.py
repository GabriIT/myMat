from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
)
from .ingest import build_vectorstore


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a new Chroma vector store from knowledge files, then optionally "
            "archive current store and promote the new one."
        )
    )
    parser.add_argument("--knowledge-root", required=True, help="Knowledge root directory.")
    parser.add_argument(
        "--active-db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"Active Chroma DB path to replace (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help=f"Collection name (default: {DEFAULT_COLLECTION_NAME}).",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"Embedding model name (default: {DEFAULT_EMBEDDING_MODEL}).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Chunk size (default: {DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help=f"Chunk overlap (default: {DEFAULT_CHUNK_OVERLAP}).",
    )
    parser.add_argument(
        "--candidate-db-path",
        help="Optional explicit candidate DB path. Default is next to active path with timestamp.",
    )
    parser.add_argument(
        "--backup-root",
        help="Optional backup root. Default is <active_parent>/vector_db_backups.",
    )
    parser.add_argument(
        "--keep-backups",
        type=int,
        default=5,
        help="Number of newest backups to keep (default: 5, 0 means keep all).",
    )
    parser.add_argument(
        "--strict-parse",
        action="store_true",
        help="Fail if parser reports any failed files.",
    )
    parser.add_argument(
        "--quiet-parser-warnings",
        action="store_true",
        help="Suppress noisy parser stderr warnings from PDF backends.",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Build candidate DB but do not archive/promote.",
    )
    return parser


def _prune_backups(backup_root: Path, keep_backups: int) -> None:
    if keep_backups <= 0 or not backup_root.exists():
        return
    backups = sorted(
        [path for path in backup_root.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in backups[keep_backups:]:
        for sub in sorted(stale.rglob("*"), reverse=True):
            if sub.is_file() or sub.is_symlink():
                sub.unlink(missing_ok=True)
            elif sub.is_dir():
                sub.rmdir()
        stale.rmdir()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    knowledge_root = Path(args.knowledge_root).expanduser().resolve()
    active_db_path = Path(args.active_db_path).expanduser().resolve()
    active_parent = active_db_path.parent
    stamp = _utc_stamp()
    candidate_db_path = (
        Path(args.candidate_db_path).expanduser().resolve()
        if args.candidate_db_path
        else active_parent / f"{active_db_path.name}_candidate_{stamp}"
    )
    backup_root = (
        Path(args.backup_root).expanduser().resolve()
        if args.backup_root
        else active_parent / "vector_db_backups"
    )

    if not knowledge_root.exists() or not knowledge_root.is_dir():
        print(f"Knowledge root does not exist or is not a directory: {knowledge_root}")
        return 2
    if candidate_db_path.exists():
        print(f"Candidate DB path already exists: {candidate_db_path}")
        return 2

    summary, parse_results = build_vectorstore(
        knowledge_root=knowledge_root,
        db_path=candidate_db_path,
        collection_name=args.collection,
        embedding_model=args.embedding_model,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        reset=True,
        quiet_parser_warnings=args.quiet_parser_warnings,
    )

    print("=== Candidate Vector Build Summary ===")
    print(f"Knowledge files parsed: {summary.parse_file_count}")
    print(f"Parsed documents: {summary.parsed_documents}")
    print(f"Chunks created: {summary.chunks}")
    print(f"Vectors in candidate collection: {summary.vector_count}")
    print(f"Status counts: {summary.parse_status_counts}")
    print(f"Candidate DB path: {candidate_db_path}")
    print(f"Collection: {summary.collection_name}")
    print(f"Embedding model: {summary.embedding_model}")

    failed_files = [result for result in parse_results if result.status == "failed"]
    if failed_files:
        print("\nFailed parser files:")
        for result in failed_files:
            print(f"- {result.source_path}")
            for issue in result.issues:
                print(f"  - {issue.code}: {issue.message}")

    if args.strict_parse and summary.failed_files > 0:
        print("Strict parse enabled and parser failures found. Candidate will not be promoted.")
        return 1
    if summary.vector_count <= 0:
        print("Candidate vector store is empty. Promotion aborted.")
        return 1
    if args.build_only:
        print("Build-only mode: candidate created and left unpromoted.")
        return 0

    backup_path: Path | None = None
    if active_db_path.exists():
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_path = backup_root / f"{active_db_path.name}_backup_{stamp}"
        active_db_path.rename(backup_path)
        print(f"Archived active DB to backup: {backup_path}")

    try:
        candidate_db_path.rename(active_db_path)
    except Exception as exc:
        print(f"Promotion failed: {exc}")
        if backup_path and backup_path.exists() and not active_db_path.exists():
            backup_path.rename(active_db_path)
            print("Rollback complete: restored previous active DB.")
        return 1

    print(f"Promoted candidate as active DB: {active_db_path}")
    if backup_path:
        print(f"Previous active DB backup: {backup_path}")
    _prune_backups(backup_root, args.keep_backups)
    if args.keep_backups > 0:
        print(f"Backup pruning applied (keep_backups={args.keep_backups}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
