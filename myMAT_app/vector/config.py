from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PACKAGE_ROOT.parent

def _env_first(names: tuple[str, ...], default: str) -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return default

DEFAULT_DB_PATH = Path(
    _env_first(("MYMAT_DB_PATH", "MYRAG_DB_PATH"), str(PROJECT_ROOT / "vector_db"))
).expanduser().resolve()
DEFAULT_COLLECTION_NAME = _env_first(("MYMAT_COLLECTION", "MYRAG_COLLECTION"), "mymat_docs")

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_CHAT_MODEL = "gpt-4.1-nano"
OLLAMA_CHAT_MODELS = (
    "qwen3.5:9b",
    "llama3.2:latest",
)
SUPPORTED_CHAT_MODELS = (DEFAULT_CHAT_MODEL, *OLLAMA_CHAT_MODELS)

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_RETRIEVAL_K = 8
DEFAULT_RETRIEVAL_SEARCH_TYPE = "mmr"
DEFAULT_RETRIEVAL_FETCH_K = 40
DEFAULT_RETRIEVAL_LAMBDA_MULT = 0.35
