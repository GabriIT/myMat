from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

from myMAT_app.vector.config import DEFAULT_EMBEDDING_MODEL

try:
    import psycopg
except Exception:  # pragma: no cover - handled at runtime if dependency missing
    psycopg = None

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_first(names: tuple[str, ...], default: str) -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is not None and raw.strip():
            return raw
    return default


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _coerce_vector_dims(value: int) -> int:
    return max(128, min(8192, int(value)))


@dataclass(slots=True)
class ThreadMemoryConfig:
    enabled: bool
    dsn: str | None
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str
    connect_timeout: int
    embedding_model: str
    vector_dims: int
    recent_messages: int
    semantic_top_k: int
    max_history_messages: int

    @classmethod
    def from_env(cls) -> "ThreadMemoryConfig":
        # Load repo/local .env when available so direct CLI runs work without manual export.
        load_dotenv(override=False)

        dsn_raw = _env_first(
            ("MYMAT_THREADS_DB_DSN", "MYMAT_THREADS_DSN", "MYRAG_THREADS_DB_DSN", "MYRAG_THREADS_DSN"),
            "",
        )
        return cls(
            enabled=_bool_env("MYMAT_THREADS_ENABLED", _bool_env("MYRAG_THREADS_ENABLED", False)),
            dsn=dsn_raw.strip() or None,
            host=_env_first(
                ("MYMAT_THREADS_DB_HOST", "MYMAT_THREADS_HOST", "MYRAG_THREADS_DB_HOST", "MYRAG_THREADS_HOST"),
                "127.0.0.1",
            ),
            port=_int_env(
                "MYMAT_THREADS_DB_PORT",
                _int_env("MYMAT_THREADS_PORT", _int_env("MYRAG_THREADS_DB_PORT", _int_env("MYRAG_THREADS_PORT", 5432, 1, 65535), 1, 65535), 1, 65535),
                1,
                65535,
            ),
            dbname=_env_first(
                ("MYMAT_THREADS_DB_NAME", "MYMAT_THREADS_DB", "MYRAG_THREADS_DB_NAME", "MYRAG_THREADS_DB"),
                "myMAT_ops",
            ),
            user=_env_first(
                ("MYMAT_THREADS_DB_USER", "MYMAT_THREADS_USER", "MYRAG_THREADS_DB_USER", "MYRAG_THREADS_USER"),
                "postgresql",
            ),
            password=_env_first(
                (
                    "MYMAT_THREADS_DB_PASSWORD",
                    "MYMAT_THREADS_PASSWORD",
                    "MYRAG_THREADS_DB_PASSWORD",
                    "MYRAG_THREADS_PASSWORD",
                ),
                "postgresql",
            ),
            sslmode=_env_first(("MYMAT_THREADS_DB_SSLMODE", "MYRAG_THREADS_DB_SSLMODE"), "disable"),
            connect_timeout=_int_env(
                "MYMAT_THREADS_DB_CONNECT_TIMEOUT",
                _int_env("MYRAG_THREADS_DB_CONNECT_TIMEOUT", 5, 1, 60),
                1,
                60,
            ),
            embedding_model=_env_first(
                ("MYMAT_THREADS_EMBEDDING_MODEL", "MYRAG_THREADS_EMBEDDING_MODEL"), DEFAULT_EMBEDDING_MODEL
            ),
            vector_dims=_coerce_vector_dims(
                _int_env(
                    "MYMAT_THREADS_VECTOR_DIMS",
                    _int_env(
                        "MYMAT_THREADS_EMBEDDING_DIMS",
                        _int_env("MYRAG_THREADS_VECTOR_DIMS", _int_env("MYRAG_THREADS_EMBEDDING_DIMS", 3072, 128, 8192), 128, 8192),
                        128,
                        8192,
                    ),
                    128,
                    8192,
                )
            ),
            recent_messages=_int_env(
                "MYMAT_THREADS_RECENT_MESSAGES",
                _int_env("MYRAG_THREADS_RECENT_MESSAGES", 10, 1, 100),
                1,
                100,
            ),
            semantic_top_k=_int_env(
                "MYMAT_THREADS_SEMANTIC_TOP_K",
                _int_env("MYRAG_THREADS_SEMANTIC_TOP_K", 6, 0, 50),
                0,
                50,
            ),
            max_history_messages=_int_env(
                "MYMAT_THREADS_MAX_HISTORY_MESSAGES",
                _int_env(
                    "MYMAT_THREADS_MAX_HISTORY",
                    _int_env("MYRAG_THREADS_MAX_HISTORY_MESSAGES", _int_env("MYRAG_THREADS_MAX_HISTORY", 24, 1, 120), 1, 120),
                    1,
                    120,
                ),
                1,
                120,
            ),
        )


class ThreadMemoryStore:
    def __init__(self, config: ThreadMemoryConfig):
        self.config = config
        self._initialized = False
        self._init_error: str | None = None
        self._embedder: OpenAIEmbeddings | None = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def _build_dsn(self) -> str:
        if self.config.dsn:
            return self.config.dsn
        return (
            f"host={self.config.host} "
            f"port={self.config.port} "
            f"dbname={self.config.dbname} "
            f"user={self.config.user} "
            f"password={self.config.password} "
            f"sslmode={self.config.sslmode} "
            f"connect_timeout={self.config.connect_timeout}"
        )

    def _connect(self):
        if psycopg is None:
            raise RuntimeError(
                "psycopg is not installed. Install with: "
                "uv pip install --python .venv/bin/python psycopg[binary]"
            )
        return psycopg.connect(self._build_dsn(), autocommit=True)

    def ensure_schema(self) -> bool:
        if not self.config.enabled:
            return False
        if self._initialized:
            return True
        dims = self.config.vector_dims
        schema_sql = f"""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS memory.thread_sessions (
          username TEXT NOT NULL,
          thread_id TEXT NOT NULL,
          title TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (username, thread_id)
        );

        CREATE TABLE IF NOT EXISTS memory.thread_messages (
          id BIGSERIAL PRIMARY KEY,
          username TEXT NOT NULL,
          thread_id TEXT NOT NULL,
          role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
          content TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          embedding vector({dims}),
          metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          CONSTRAINT fk_thread_session
            FOREIGN KEY (username, thread_id)
            REFERENCES memory.thread_sessions (username, thread_id)
            ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_memory_thread_messages_lookup
          ON memory.thread_messages (username, thread_id, created_at, id);
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
                    # IVFFlat currently supports up to 2000 dimensions.
                    # Keep thread memory functional for larger embeddings by skipping this index.
                    if dims <= 2000:
                        cur.execute(
                            """
                            CREATE INDEX IF NOT EXISTS idx_memory_thread_messages_embedding
                              ON memory.thread_messages USING ivfflat (embedding vector_cosine_ops)
                              WITH (lists = 100);
                            """
                        )
            self._initialized = True
            self._init_error = None
            return True
        except Exception as exc:  # pragma: no cover - depends on local DB availability
            self._init_error = str(exc)
            logger.warning("Thread memory schema init failed: %s", exc)
            return False

    def health(self) -> dict[str, Any]:
        ready = self.ensure_schema()
        return {
            "enabled": self.config.enabled,
            "ready": ready,
            "db_name": self.config.dbname,
            "last_error": self._init_error,
            "vector_dims": self.config.vector_dims,
            "embedding_model": self.config.embedding_model,
        }

    def _get_embedder(self) -> OpenAIEmbeddings:
        if self._embedder is None:
            load_dotenv(override=True)
            self._embedder = OpenAIEmbeddings(model=self.config.embedding_model)
        return self._embedder

    def _embed_text(self, text: str) -> list[float] | None:
        if not text.strip():
            return None
        try:
            return self._get_embedder().embed_query(text)
        except Exception as exc:  # pragma: no cover - network/provider failures
            logger.warning("Thread memory embedding failed: %s", exc)
            return None

    @staticmethod
    def _vector_literal(vector: list[float] | None) -> str | None:
        if not vector:
            return None
        return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"

    def _upsert_thread(
        self,
        *,
        conn,
        username: str,
        thread_id: str,
        title: str,
    ) -> None:
        normalized_title = (title or "").strip() or "New Thread"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memory.thread_sessions (username, thread_id, title)
                VALUES (%s, %s, %s)
                ON CONFLICT (username, thread_id)
                DO UPDATE SET
                  updated_at = now(),
                  title = CASE
                    WHEN memory.thread_sessions.title IS NULL
                      OR btrim(memory.thread_sessions.title) = ''
                      OR memory.thread_sessions.title = 'New Thread'
                    THEN COALESCE(NULLIF(btrim(EXCLUDED.title), ''), 'New Thread')
                    ELSE memory.thread_sessions.title
                  END
                """,
                (username, thread_id, normalized_title),
            )

    @staticmethod
    def _normalize_title(value: str | None) -> str:
        clean = (value or "").strip()
        return clean or "New Thread"

    @staticmethod
    def _summary_from_row(row: Any) -> dict[str, Any]:
        return {
            "thread_id": str(row[0]),
            "title": ThreadMemoryStore._normalize_title(str(row[1]) if row[1] is not None else None),
            "created_at": row[2],
            "updated_at": row[3],
            "message_count": int(row[4] or 0),
            "last_message_preview": str(row[5]) if row[5] is not None else None,
        }

    @staticmethod
    def _coerce_metadata_dict(raw: Any) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _coerce_sources(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        sources: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            sources.append(
                {
                    "source": str(item.get("source", "unknown")),
                    "source_name": str(item.get("source_name", "unknown")),
                    "doc_type": str(item.get("doc_type", "unknown")),
                    "page_number": item.get("page_number"),
                    "sheet_name": item.get("sheet_name"),
                }
            )
        return sources

    @staticmethod
    def _coerce_structured(raw: Any, fallback_content: str) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        prompt = str(raw.get("prompt", "")).strip()
        answer_text = str(raw.get("answer_text", "")).strip()
        bullets_raw = raw.get("bullets")
        bullets: list[str] = []
        if isinstance(bullets_raw, list):
            bullets = [str(item).strip() for item in bullets_raw if str(item).strip()]
        if not prompt and not answer_text and not bullets:
            return None
        return {
            "prompt": prompt or "Thread follow-up",
            "bullets": bullets,
            "answer_text": answer_text or fallback_content,
        }

    def list_threads(self, *, username: str, limit: int = 50) -> list[dict[str, Any]]:
        if not self.ensure_schema():
            raise RuntimeError("Thread memory schema is not ready.")
        capped_limit = max(1, min(200, int(limit)))
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                          s.thread_id,
                          COALESCE(NULLIF(btrim(s.title), ''), 'New Thread') AS title,
                          s.created_at,
                          s.updated_at,
                          (
                            SELECT count(*)::int
                            FROM memory.thread_messages m
                            WHERE m.username = s.username
                              AND m.thread_id = s.thread_id
                          ) AS message_count,
                          (
                            SELECT left(m2.content, 180)
                            FROM memory.thread_messages m2
                            WHERE m2.username = s.username
                              AND m2.thread_id = s.thread_id
                            ORDER BY m2.created_at DESC, m2.id DESC
                            LIMIT 1
                          ) AS last_message_preview
                        FROM memory.thread_sessions s
                        WHERE s.username = %s
                        ORDER BY s.updated_at DESC, s.created_at DESC
                        LIMIT %s
                        """,
                        (username, capped_limit),
                    )
                    rows = cur.fetchall()
            return [self._summary_from_row(row) for row in rows]
        except Exception as exc:  # pragma: no cover - depends on DB runtime
            raise RuntimeError(f"Failed to list threads: {exc}") from exc

    def get_thread_summary(self, *, username: str, thread_id: str) -> dict[str, Any] | None:
        if not self.ensure_schema():
            raise RuntimeError("Thread memory schema is not ready.")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                          s.thread_id,
                          COALESCE(NULLIF(btrim(s.title), ''), 'New Thread') AS title,
                          s.created_at,
                          s.updated_at,
                          (
                            SELECT count(*)::int
                            FROM memory.thread_messages m
                            WHERE m.username = s.username
                              AND m.thread_id = s.thread_id
                          ) AS message_count,
                          (
                            SELECT left(m2.content, 180)
                            FROM memory.thread_messages m2
                            WHERE m2.username = s.username
                              AND m2.thread_id = s.thread_id
                            ORDER BY m2.created_at DESC, m2.id DESC
                            LIMIT 1
                          ) AS last_message_preview
                        FROM memory.thread_sessions s
                        WHERE s.username = %s
                          AND s.thread_id = %s
                        LIMIT 1
                        """,
                        (username, thread_id),
                    )
                    row = cur.fetchone()
            if row is None:
                return None
            return self._summary_from_row(row)
        except Exception as exc:  # pragma: no cover - depends on DB runtime
            raise RuntimeError(f"Failed to get thread summary: {exc}") from exc

    def create_thread(
        self,
        *,
        username: str,
        thread_id: str,
        title: str | None = None,
    ) -> dict[str, Any]:
        if not self.ensure_schema():
            raise RuntimeError("Thread memory schema is not ready.")
        thread_title = self._normalize_title(title)
        try:
            with self._connect() as conn:
                self._upsert_thread(
                    conn=conn,
                    username=username,
                    thread_id=thread_id,
                    title=thread_title,
                )
            summary = self.get_thread_summary(username=username, thread_id=thread_id)
            if summary is None:
                raise RuntimeError("Thread was not found after creation.")
            return summary
        except Exception as exc:  # pragma: no cover - depends on DB runtime
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"Failed to create thread: {exc}") from exc

    def rename_thread(
        self,
        *,
        username: str,
        thread_id: str,
        title: str,
    ) -> dict[str, Any] | None:
        if not self.ensure_schema():
            raise RuntimeError("Thread memory schema is not ready.")
        new_title = self._normalize_title(title)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE memory.thread_sessions
                        SET title = %s,
                            updated_at = now()
                        WHERE username = %s
                          AND thread_id = %s
                        """,
                        (new_title, username, thread_id),
                    )
            return self.get_thread_summary(username=username, thread_id=thread_id)
        except Exception as exc:  # pragma: no cover - depends on DB runtime
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"Failed to rename thread: {exc}") from exc

    def delete_thread(
        self,
        *,
        username: str,
        thread_id: str,
    ) -> bool:
        if not self.ensure_schema():
            raise RuntimeError("Thread memory schema is not ready.")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM memory.thread_sessions
                        WHERE username = %s
                          AND thread_id = %s
                        """,
                        (username, thread_id),
                    )
                    deleted_count = int(cur.rowcount or 0)
            return deleted_count > 0
        except Exception as exc:  # pragma: no cover - depends on DB runtime
            raise RuntimeError(f"Failed to delete thread: {exc}") from exc

    def get_thread_messages(
        self,
        *,
        username: str,
        thread_id: str,
        limit: int = 500,
    ) -> dict[str, Any] | None:
        if not self.ensure_schema():
            raise RuntimeError("Thread memory schema is not ready.")
        capped_limit = max(1, min(1000, int(limit)))
        summary = self.get_thread_summary(username=username, thread_id=thread_id)
        if summary is None:
            return None
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, role, content, created_at, metadata
                        FROM memory.thread_messages
                        WHERE username = %s
                          AND thread_id = %s
                        ORDER BY created_at ASC, id ASC
                        LIMIT %s
                        """,
                        (username, thread_id, capped_limit),
                    )
                    rows = cur.fetchall()
            messages: list[dict[str, Any]] = []
            for row in rows:
                metadata = self._coerce_metadata_dict(row[4])
                message: dict[str, Any] = {
                    "id": int(row[0]),
                    "role": str(row[1]),
                    "content": str(row[2]),
                    "created_at": row[3],
                    "sources": [],
                }
                if str(row[1]) == "assistant":
                    structured = self._coerce_structured(metadata.get("structured"), str(row[2]))
                    if structured is not None:
                        message["structured"] = structured
                    message["sources"] = self._coerce_sources(metadata.get("sources"))
                messages.append(message)
            return {"thread": summary, "messages": messages}
        except Exception as exc:  # pragma: no cover - depends on DB runtime
            raise RuntimeError(f"Failed to get thread messages: {exc}") from exc

    def _insert_message(
        self,
        *,
        conn,
        username: str,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        embedding_literal = self._vector_literal(self._embed_text(content))
        with conn.cursor() as cur:
            if embedding_literal:
                cur.execute(
                    """
                    INSERT INTO memory.thread_messages
                      (username, thread_id, role, content, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb)
                    """,
                    (username, thread_id, role, content, embedding_literal, payload),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO memory.thread_messages
                      (username, thread_id, role, content, metadata)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (username, thread_id, role, content, payload),
                )

    def persist_turn(
        self,
        *,
        username: str,
        thread_id: str,
        question: str,
        answer: str,
        assistant_metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not self.ensure_schema():
            return False
        title = question.strip().replace("\n", " ")
        if len(title) > 80:
            title = f"{title[:80]}..."
        try:
            with self._connect() as conn:
                self._upsert_thread(conn=conn, username=username, thread_id=thread_id, title=title)
                self._insert_message(
                    conn=conn,
                    username=username,
                    thread_id=thread_id,
                    role="user",
                    content=question,
                    metadata={"type": "question"},
                )
                self._insert_message(
                    conn=conn,
                    username=username,
                    thread_id=thread_id,
                    role="assistant",
                    content=answer,
                    metadata=assistant_metadata or {},
                )
            return True
        except Exception as exc:  # pragma: no cover - depends on DB runtime
            logger.warning("Thread memory persist failed: %s", exc)
            return False

    def _fetch_recent_messages(self, *, username: str, thread_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, role, content, created_at
                    FROM memory.thread_messages
                    WHERE username = %s AND thread_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (username, thread_id, self.config.recent_messages),
                )
                rows = cur.fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            messages.append(
                {
                    "id": int(row[0]),
                    "role": str(row[1]),
                    "content": str(row[2]),
                    "created_at": row[3],
                }
            )
        messages.reverse()
        return messages

    def _fetch_semantic_messages(
        self,
        *,
        username: str,
        thread_id: str,
        question: str,
    ) -> list[dict[str, Any]]:
        if self.config.semantic_top_k <= 0:
            return []
        query_vector = self._vector_literal(self._embed_text(question))
        if not query_vector:
            return []
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, role, content, created_at
                    FROM memory.thread_messages
                    WHERE username = %s
                      AND thread_id = %s
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (username, thread_id, query_vector, self.config.semantic_top_k),
                )
                rows = cur.fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            messages.append(
                {
                    "id": int(row[0]),
                    "role": str(row[1]),
                    "content": str(row[2]),
                    "created_at": row[3],
                }
            )
        return messages

    def build_history(
        self,
        *,
        username: str,
        thread_id: str,
        question: str,
        fallback_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        if not self.ensure_schema():
            return list(fallback_history or [])
        try:
            recent = self._fetch_recent_messages(username=username, thread_id=thread_id)
            semantic = self._fetch_semantic_messages(
                username=username, thread_id=thread_id, question=question
            )
        except Exception as exc:  # pragma: no cover - depends on DB runtime
            logger.warning("Thread memory read failed: %s", exc)
            return list(fallback_history or [])

        by_id: dict[int, dict[str, Any]] = {}
        for msg in semantic:
            by_id[msg["id"]] = msg
        for msg in recent:
            by_id[msg["id"]] = msg

        ordered = sorted(
            by_id.values(),
            key=lambda item: (
                item["created_at"] if isinstance(item["created_at"], datetime) else datetime.min,
                item["id"],
            ),
        )
        history = [{"role": item["role"], "content": item["content"]} for item in ordered]

        if not history:
            return list(fallback_history or [])

        if fallback_history:
            seen = {(item["role"], item["content"]) for item in history}
            for item in fallback_history:
                role = str(item.get("role", "")).strip()
                content = str(item.get("content", "")).strip()
                if role not in {"user", "assistant"} or not content:
                    continue
                key = (role, content)
                if key not in seen:
                    history.append({"role": role, "content": content})
                    seen.add(key)

        if len(history) > self.config.max_history_messages:
            history = history[-self.config.max_history_messages :]
        return history


def create_thread_memory_store_from_env() -> ThreadMemoryStore:
    return ThreadMemoryStore(ThreadMemoryConfig.from_env())
