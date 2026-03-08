from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .parser_config import ParseConfig
from .parsers import parse_knowledge_base


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a knowledge folder and export chunked documents to JSONL "
            "for vector database ingestion."
        )
    )
    parser.add_argument(
        "--knowledge-root",
        required=True,
        help="Path to the root knowledge folder.",
    )
    parser.add_argument(
        "--output-path",
        required=True,
        help="Path to JSONL output file.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Chunk size for RecursiveCharacterTextSplitter (default: 1000).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Chunk overlap for RecursiveCharacterTextSplitter (default: 200).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any file parsing fails.",
    )
    return parser


def _chunk_id(metadata: dict, chunk_index: int) -> str:
    key = "|".join(
        [
            str(metadata.get("source", "")),
            str(metadata.get("source_name", "")),
            str(metadata.get("page_number", "")),
            str(metadata.get("sheet_name", "")),
            str(metadata.get("slide_number", "")),
            str(chunk_index),
        ]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = ParseConfig(knowledge_root=Path(args.knowledge_root), strict_mode=args.strict)

    try:
        documents, results = parse_knowledge_base(config)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"Validation error: {exc}")
        return 2

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    chunks = splitter.split_documents(documents)

    output_path = Path(args.output_path)
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

    failed_count = sum(1 for result in results if result.status == "failed")
    warning_count = sum(1 for result in results if result.status == "warning")

    print("=== Chunk Export Summary ===")
    print(f"Input docs parsed: {len(documents)}")
    print(f"Chunks written: {len(chunks)}")
    print(f"Warnings: {warning_count}")
    print(f"Failures: {failed_count}")
    print(f"Output: {output_path}")

    if config.strict_mode and failed_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
