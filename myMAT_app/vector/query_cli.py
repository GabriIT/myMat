from __future__ import annotations

import argparse
from pathlib import Path

from .answer import answer_question
from .config import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RETRIEVAL_FETCH_K,
    DEFAULT_RETRIEVAL_K,
    DEFAULT_RETRIEVAL_LAMBDA_MULT,
    DEFAULT_RETRIEVAL_SEARCH_TYPE,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query local myMAT Chroma vectorstore with RAG.")
    parser.add_argument("--question", required=True, help="Question to ask.")
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
        help=f"Embedding model (default: {DEFAULT_EMBEDDING_MODEL}).",
    )
    parser.add_argument(
        "--chat-model",
        default=DEFAULT_CHAT_MODEL,
        help=f"Chat model (default: {DEFAULT_CHAT_MODEL}).",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_RETRIEVAL_K,
        help=f"Number of retrieved chunks (default: {DEFAULT_RETRIEVAL_K}).",
    )
    parser.add_argument(
        "--search-type",
        choices=["similarity", "mmr"],
        default=DEFAULT_RETRIEVAL_SEARCH_TYPE,
        help=f"Retriever search type (default: {DEFAULT_RETRIEVAL_SEARCH_TYPE}).",
    )
    parser.add_argument(
        "--fetch-k",
        type=int,
        default=DEFAULT_RETRIEVAL_FETCH_K,
        help=f"MMR candidate pool size (default: {DEFAULT_RETRIEVAL_FETCH_K}).",
    )
    parser.add_argument(
        "--lambda-mult",
        type=float,
        default=DEFAULT_RETRIEVAL_LAMBDA_MULT,
        help=f"MMR diversity factor 0..1 (default: {DEFAULT_RETRIEVAL_LAMBDA_MULT}).",
    )
    parser.add_argument(
        "--doc-type",
        help="Optional metadata filter: doc_type equals this value.",
    )
    parser.add_argument(
        "--source-contains",
        help="Optional source filename/path substring filter.",
    )
    parser.add_argument(
        "--show-context",
        action="store_true",
        help="Print retrieved chunks.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    answer, docs = answer_question(
        args.question,
        db_path=Path(args.db_path),
        collection_name=args.collection,
        embedding_model=args.embedding_model,
        chat_model=args.chat_model,
        k=args.k,
        search_type=args.search_type,
        fetch_k=args.fetch_k,
        lambda_mult=args.lambda_mult,
        doc_type=args.doc_type,
        source_contains=args.source_contains,
    )

    print("=== Answer ===")
    print(answer)
    print("\n=== Sources ===")
    for idx, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        doc_type = doc.metadata.get("doc_type", "unknown")
        page = doc.metadata.get("page_number")
        sheet = doc.metadata.get("sheet_name")
        suffix = f" page={page}" if page else ""
        suffix += f" sheet={sheet}" if sheet else ""
        print(f"{idx}. {source} doc_type={doc_type}{suffix}")

    if args.show_context:
        print("\n=== Retrieved Context ===")
        for idx, doc in enumerate(docs, start=1):
            print(f"[{idx}] {doc.page_content[:1200]}")
            print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
