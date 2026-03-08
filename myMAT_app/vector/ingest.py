from __future__ import annotations

import contextlib
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from myMAT_app.parser.parser_config import ParseConfig
from myMAT_app.parser.parser_types import FileParseResult
from myMAT_app.parser.parsers import parse_knowledge_base

from .config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
)


@dataclass(slots=True)
class IngestSummary:
    parsed_documents: int
    parse_file_count: int
    chunks: int
    vector_count: int
    parse_status_counts: dict[str, int]
    warning_files: int
    failed_files: int
    db_path: str
    collection_name: str
    embedding_model: str


def _safe_collection_count(vectorstore: Chroma) -> int:
    try:
        return int(vectorstore._collection.count())
    except Exception:
        return 0


def build_vectorstore(
    *,
    knowledge_root: Path,
    db_path: Path = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    reset: bool = False,
    quiet_parser_warnings: bool = False,
) -> tuple[IngestSummary, list[FileParseResult]]:
    load_dotenv(override=True)

    parse_config = ParseConfig(knowledge_root=knowledge_root)
    if quiet_parser_warnings:
        with open(os.devnull, "w", encoding="utf-8") as devnull, contextlib.redirect_stderr(
            devnull
        ):
            parsed_documents, parse_results = parse_knowledge_base(parse_config)
    else:
        parsed_documents, parse_results = parse_knowledge_base(parse_config)
    status_counts = Counter(result.status for result in parse_results)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(parsed_documents)

    db_path = Path(db_path).expanduser().resolve()
    db_path.mkdir(parents=True, exist_ok=True)
    embeddings = OpenAIEmbeddings(model=embedding_model)

    vectorstore = Chroma(
        persist_directory=str(db_path),
        embedding_function=embeddings,
        collection_name=collection_name,
    )

    if reset:
        try:
            vectorstore.delete_collection()
        except Exception:
            # Collection might not exist yet.
            pass

    if chunks:
        if reset or _safe_collection_count(vectorstore) == 0:
            vectorstore = Chroma.from_documents(
                documents=chunks,
                embedding=embeddings,
                persist_directory=str(db_path),
                collection_name=collection_name,
            )
        else:
            vectorstore.add_documents(chunks)

    summary = IngestSummary(
        parsed_documents=len(parsed_documents),
        parse_file_count=len(parse_results),
        chunks=len(chunks),
        vector_count=_safe_collection_count(vectorstore),
        parse_status_counts=dict(sorted(status_counts.items())),
        warning_files=status_counts.get("warning", 0),
        failed_files=status_counts.get("failed", 0),
        db_path=str(db_path),
        collection_name=collection_name,
        embedding_model=embedding_model,
    )
    return summary, parse_results
