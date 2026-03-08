from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from .config import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RETRIEVAL_FETCH_K,
    DEFAULT_RETRIEVAL_K,
    DEFAULT_RETRIEVAL_LAMBDA_MULT,
    DEFAULT_RETRIEVAL_SEARCH_TYPE,
)


def load_vectorstore(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> Chroma:
    load_dotenv(override=True)
    embeddings = OpenAIEmbeddings(model=embedding_model)
    return Chroma(
        persist_directory=str(Path(db_path).expanduser().resolve()),
        embedding_function=embeddings,
        collection_name=collection_name,
    )


def retrieve_context(
    question: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    k: int = DEFAULT_RETRIEVAL_K,
    search_type: str = DEFAULT_RETRIEVAL_SEARCH_TYPE,
    fetch_k: int = DEFAULT_RETRIEVAL_FETCH_K,
    lambda_mult: float = DEFAULT_RETRIEVAL_LAMBDA_MULT,
    doc_type: str | None = None,
    source_contains: str | None = None,
) -> list[Document]:
    vectorstore = load_vectorstore(
        db_path=db_path,
        collection_name=collection_name,
        embedding_model=embedding_model,
    )
    if search_type not in {"similarity", "mmr"}:
        raise ValueError("search_type must be one of: similarity, mmr")

    search_kwargs: dict[str, object] = {"k": k}
    if doc_type:
        search_kwargs["filter"] = {"doc_type": doc_type}
    if search_type == "mmr":
        search_kwargs["fetch_k"] = max(fetch_k, k)
        search_kwargs["lambda_mult"] = lambda_mult

    retriever = vectorstore.as_retriever(
        search_type=search_type,
        search_kwargs=search_kwargs,
    )
    docs = retriever.invoke(question)

    if source_contains:
        needle = source_contains.lower()
        filtered_docs = []
        for doc in docs:
            source = str(doc.metadata.get("source", "")).lower()
            source_name = str(doc.metadata.get("source_name", "")).lower()
            if needle in source or needle in source_name:
                filtered_docs.append(doc)
        if filtered_docs:
            docs = filtered_docs

    return docs
