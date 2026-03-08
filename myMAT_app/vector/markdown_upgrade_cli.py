from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, DEFAULT_EMBEDDING_MODEL, PROJECT_ROOT

DEFAULT_MARKDOWN_ROOT = PROJECT_ROOT / "markdown_knowledge"
DEFAULT_MARKDOWN_DB_PATH = PROJECT_ROOT / "vector_db_markdown"
DEFAULT_MARKDOWN_COLLECTION = "myrag_docs_markdown"
DEFAULT_ACTIVE_DB_PATH = os.getenv(
    "MYMAT_DB_PATH", os.getenv("MYRAG_DB_PATH", str(DEFAULT_MARKDOWN_DB_PATH))
)
DEFAULT_ACTIVE_COLLECTION = os.getenv(
    "MYMAT_COLLECTION", os.getenv("MYRAG_COLLECTION", DEFAULT_MARKDOWN_COLLECTION)
)


@dataclass(slots=True)
class MarkdownUpgradeSummary:
    markdown_files: int
    chunks: int
    vector_count: int
    markdown_root: str
    active_db_path: str
    collection_name: str
    embedding_model: str


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a markdown-based candidate vector store from markdown_knowledge, then "
            "archive current active markdown DB and promote candidate."
        )
    )
    parser.add_argument(
        "--markdown-root",
        default=str(DEFAULT_MARKDOWN_ROOT),
        help=f"Markdown root directory (default: {DEFAULT_MARKDOWN_ROOT}).",
    )
    parser.add_argument(
        "--active-db-path",
        default=str(DEFAULT_ACTIVE_DB_PATH),
        help=f"Active markdown DB path to replace (default: {DEFAULT_ACTIVE_DB_PATH}).",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_ACTIVE_COLLECTION,
        help=f"Collection name (default: {DEFAULT_ACTIVE_COLLECTION}).",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"Embedding model (default: {DEFAULT_EMBEDDING_MODEL}).",
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
        help="Optional explicit candidate DB path. Default is active path with timestamp suffix.",
    )
    parser.add_argument(
        "--backup-root",
        help="Optional backup root. Default is <active_parent>/vector_db_markdown_backups.",
    )
    parser.add_argument(
        "--keep-backups",
        type=int,
        default=5,
        help="Number of newest backups to keep (default: 5, 0 means keep all).",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Build candidate DB but do not archive/promote.",
    )
    return parser


def _load_markdown_documents(markdown_root: Path) -> list[Document]:
    docs: list[Document] = []
    for path in sorted(markdown_root.glob("*.md"), key=lambda p: p.name.casefold()):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source": str(path),
                    "source_name": path.name,
                    "source_ext": ".md",
                    "doc_type": path.stem,
                },
            )
        )
    return docs


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


def _build_candidate(
    *,
    markdown_root: Path,
    candidate_db_path: Path,
    collection_name: str,
    embedding_model: str,
    chunk_size: int,
    chunk_overlap: int,
) -> MarkdownUpgradeSummary:
    docs = _load_markdown_documents(markdown_root)
    if not docs:
        raise ValueError(f"No markdown files found in {markdown_root}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(docs)
    if not chunks:
        raise ValueError("No chunks produced from markdown files.")

    load_dotenv(override=True)
    embeddings = OpenAIEmbeddings(model=embedding_model)
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(candidate_db_path),
        collection_name=collection_name,
    )
    vector_count = int(vectorstore._collection.count())

    return MarkdownUpgradeSummary(
        markdown_files=len(docs),
        chunks=len(chunks),
        vector_count=vector_count,
        markdown_root=str(markdown_root),
        active_db_path=str(candidate_db_path),
        collection_name=collection_name,
        embedding_model=embedding_model,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    markdown_root = Path(args.markdown_root).expanduser().resolve()
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
        else active_parent / "vector_db_markdown_backups"
    )

    if not markdown_root.exists() or not markdown_root.is_dir():
        print(f"Markdown root does not exist or is not a directory: {markdown_root}")
        return 2
    if candidate_db_path.exists():
        print(f"Candidate DB path already exists: {candidate_db_path}")
        return 2

    try:
        summary = _build_candidate(
            markdown_root=markdown_root,
            candidate_db_path=candidate_db_path,
            collection_name=args.collection,
            embedding_model=args.embedding_model,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
    except Exception as exc:
        print(f"Candidate build failed: {exc}")
        return 1

    print("=== Markdown Candidate Vector Build Summary ===")
    print(f"Markdown files parsed: {summary.markdown_files}")
    print(f"Chunks created: {summary.chunks}")
    print(f"Vectors in candidate collection: {summary.vector_count}")
    print(f"Markdown root: {markdown_root}")
    print(f"Candidate DB path: {candidate_db_path}")
    print(f"Collection: {summary.collection_name}")
    print(f"Embedding model: {summary.embedding_model}")

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
        print(f"Archived active markdown DB to backup: {backup_path}")

    try:
        candidate_db_path.rename(active_db_path)
    except Exception as exc:
        print(f"Promotion failed: {exc}")
        if backup_path and backup_path.exists() and not active_db_path.exists():
            backup_path.rename(active_db_path)
            print("Rollback complete: restored previous active markdown DB.")
        return 1

    print(f"Promoted candidate as active markdown DB: {active_db_path}")
    if backup_path:
        print(f"Previous active markdown DB backup: {backup_path}")
    _prune_backups(backup_root, args.keep_backups)
    if args.keep_backups > 0:
        print(f"Backup pruning applied (keep_backups={args.keep_backups}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
