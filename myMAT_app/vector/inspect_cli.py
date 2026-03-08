from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from langchain_chroma import Chroma

from .config import DEFAULT_COLLECTION_NAME, DEFAULT_DB_PATH


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect local Chroma collection content and metadata."
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"Chroma persist directory (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help=f"Collection name (default: {DEFAULT_COLLECTION_NAME}).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=3,
        help="Number of sample items to print (default: 3).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    db_path = Path(args.db_path).expanduser().resolve()
    if not db_path.exists():
        print(f"DB path does not exist: {db_path}")
        return 2

    vectorstore = Chroma(
        persist_directory=str(db_path),
        collection_name=args.collection,
    )
    collection = vectorstore._collection
    count = int(collection.count())

    print("=== Chroma Inspect ===")
    print(f"DB path: {db_path}")
    print(f"Collection: {args.collection}")
    print(f"Vector count: {count}")

    if count == 0:
        print("Collection is empty.")
        return 0

    sample_size = max(1, min(args.sample, count))
    data = collection.get(limit=sample_size, include=["metadatas", "documents"])
    metadatas = data.get("metadatas") or []
    documents = data.get("documents") or []
    ids = data.get("ids") or []

    key_counter = Counter(
        key for metadata in metadatas if isinstance(metadata, dict) for key in metadata
    )
    if key_counter:
        print("Metadata keys:")
        for key, freq in key_counter.most_common():
            print(f"- {key}: {freq}")

    print("\nSamples:")
    for idx in range(sample_size):
        sample_id = ids[idx] if idx < len(ids) else "<no-id>"
        metadata = metadatas[idx] if idx < len(metadatas) else {}
        document = documents[idx] if idx < len(documents) else ""
        source = metadata.get("source", "unknown") if isinstance(metadata, dict) else "unknown"
        doc_type = (
            metadata.get("doc_type", "unknown") if isinstance(metadata, dict) else "unknown"
        )
        print(f"{idx + 1}. id={sample_id} source={source} doc_type={doc_type}")
        print(f"   text={str(document)[:220]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

