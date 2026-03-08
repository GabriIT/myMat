from __future__ import annotations

import argparse
from pathlib import Path

from .config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
)
from .ingest import build_vectorstore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build/update local Chroma vectorstore from parsed myMAT knowledge."
    )
    parser.add_argument("--knowledge-root", required=True, help="Knowledge root directory.")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"Chroma persist directory (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help=f"Chroma collection name (default: {DEFAULT_COLLECTION_NAME}).",
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
        "--reset",
        action="store_true",
        help="Delete existing collection before ingesting.",
    )
    parser.add_argument(
        "--strict-parse",
        action="store_true",
        help="Return exit code 1 if parser reported any failed files.",
    )
    parser.add_argument(
        "--quiet-parser-warnings",
        action="store_true",
        help="Suppress noisy parser stderr warnings from PDF backends.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    summary, parse_results = build_vectorstore(
        knowledge_root=Path(args.knowledge_root),
        db_path=Path(args.db_path),
        collection_name=args.collection,
        embedding_model=args.embedding_model,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        reset=args.reset,
        quiet_parser_warnings=args.quiet_parser_warnings,
    )

    print("=== Vector Ingestion Summary ===")
    print(f"Knowledge files parsed: {summary.parse_file_count}")
    print(f"Parsed documents: {summary.parsed_documents}")
    print(f"Chunks created: {summary.chunks}")
    print(f"Vectors in collection: {summary.vector_count}")
    print(f"Status counts: {summary.parse_status_counts}")
    print(f"DB path: {summary.db_path}")
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
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
