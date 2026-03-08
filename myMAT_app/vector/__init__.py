"""Vectorstore modules for myMAT_app."""

from .config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RETRIEVAL_K,
    DEFAULT_RETRIEVAL_SEARCH_TYPE,
    DEFAULT_RETRIEVAL_FETCH_K,
    DEFAULT_RETRIEVAL_LAMBDA_MULT,
    DEFAULT_CHAT_MODEL,
)
from .ingest import IngestSummary, build_vectorstore
from .retrieval import load_vectorstore, retrieve_context
from .answer import answer_question

__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_COLLECTION_NAME",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_CHAT_MODEL",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_RETRIEVAL_K",
    "DEFAULT_RETRIEVAL_SEARCH_TYPE",
    "DEFAULT_RETRIEVAL_FETCH_K",
    "DEFAULT_RETRIEVAL_LAMBDA_MULT",
    "IngestSummary",
    "build_vectorstore",
    "load_vectorstore",
    "retrieve_context",
    "answer_question",
]
