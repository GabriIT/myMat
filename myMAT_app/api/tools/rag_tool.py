from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from myMAT_app.vector.answer import answer_question_structured
from myMAT_app.vector.config import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
)


def _rag_env() -> tuple[Path, str]:
    db_path = Path(os.getenv("MYMAT_DB_PATH", os.getenv("MYRAG_DB_PATH", str(DEFAULT_DB_PATH)))).expanduser().resolve()
    collection = os.getenv("MYMAT_COLLECTION", os.getenv("MYRAG_COLLECTION", DEFAULT_COLLECTION_NAME))
    return db_path, collection


def rag_answer(
    *,
    question: str,
    history: list[dict[str, str]] | None,
    chat_model: str | None,
    retrieval: dict[str, Any] | None,
) -> dict[str, Any]:
    db_path, collection = _rag_env()
    retrieval = retrieval or {}
    structured, answer, docs = answer_question_structured(
        question,
        history=history,
        db_path=db_path,
        collection_name=collection,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        chat_model=chat_model or DEFAULT_CHAT_MODEL,
        k=int(retrieval.get("k", 8)),
        search_type=str(retrieval.get("search_type", "mmr")),
        fetch_k=int(retrieval.get("fetch_k", 40)),
        lambda_mult=float(retrieval.get("lambda_mult", 0.35)),
        doc_type=retrieval.get("doc_type"),
        source_contains=retrieval.get("source_contains"),
    )

    sources: list[dict[str, Any]] = []
    seen = set()
    for doc in docs:
        metadata = doc.metadata or {}
        item = {
            "source": str(metadata.get("source", "unknown")),
            "source_name": str(metadata.get("source_name", "unknown")),
            "doc_type": str(metadata.get("doc_type", "unknown")),
            "page_number": metadata.get("page_number"),
            "sheet_name": metadata.get("sheet_name"),
        }
        key = (item["source"], item["page_number"], item["sheet_name"])
        if key in seen:
            continue
        seen.add(key)
        sources.append(item)

    confidence = "high" if len(sources) >= 3 and "I do not know" not in answer else "medium"
    if not sources or "I do not know" in answer:
        confidence = "low"

    return {
        "answer": answer,
        "structured": {
            "prompt": structured.prompt,
            "bullets": structured.bullets,
            "answer_text": structured.answer_text,
        },
        "sources": sources,
        "confidence": confidence,
    }
