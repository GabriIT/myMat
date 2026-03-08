from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from myMAT_app.api.server import create_app
from myMAT_app.vector.answer import StructuredRagAnswer


class ApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_health_ok(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("collection", payload)
        self.assertIn("db_path", payload)
        self.assertIn("thread_memory_enabled", payload)
        self.assertIn("thread_memory_ready", payload)

    @patch.dict("os.environ", {"MYRAG_ALLOWED_ORIGINS": "http://154.12.245.254,http://example.com"})
    def test_allowed_origins_from_env(self) -> None:
        app = create_app()
        cors_middlewares = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
        self.assertEqual(len(cors_middlewares), 1)
        allow_origins = cors_middlewares[0].kwargs.get("allow_origins", [])
        self.assertEqual(allow_origins, ["http://154.12.245.254", "http://example.com"])

    def test_list_threads_success(self) -> None:
        now = datetime.now(timezone.utc)
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            list_threads=lambda **_: [
                {
                    "thread_id": "thread-1",
                    "title": "First thread",
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 2,
                    "last_message_preview": "Latest answer",
                }
            ],
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.get("/api/threads", params={"username": "alice", "limit": 10})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["threads"]), 1)
        self.assertEqual(payload["threads"][0]["thread_id"], "thread-1")
        self.assertEqual(payload["threads"][0]["message_count"], 2)

    def test_create_thread_success(self) -> None:
        now = datetime.now(timezone.utc)
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            create_thread=lambda **_: {
                "thread_id": "thread-new",
                "title": "New Thread",
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
                "last_message_preview": None,
            },
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.post(
                "/api/threads",
                json={"username": "alice"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["thread"]["thread_id"], "thread-new")
        self.assertEqual(payload["thread"]["message_count"], 0)

    def test_get_thread_messages_success(self) -> None:
        now = datetime.now(timezone.utc)
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            get_thread_messages=lambda **_: {
                "thread": {
                    "thread_id": "thread-1",
                    "title": "First thread",
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 2,
                    "last_message_preview": "latest",
                },
                "messages": [
                    {
                        "id": 1,
                        "role": "user",
                        "content": "question",
                        "created_at": now,
                        "sources": [],
                    },
                    {
                        "id": 2,
                        "role": "assistant",
                        "content": "answer",
                        "created_at": now,
                        "structured": {
                            "prompt": "question",
                            "bullets": ["point"],
                            "answer_text": "answer",
                        },
                        "sources": [
                            {
                                "source": "/tmp/doc.pdf",
                                "source_name": "doc.pdf",
                                "doc_type": "Certifications",
                            }
                        ],
                    },
                ],
            },
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.get(
                "/api/threads/thread-1/messages",
                params={"username": "alice"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["thread"]["thread_id"], "thread-1")
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][1]["role"], "assistant")
        self.assertEqual(payload["messages"][1]["structured"]["prompt"], "question")
        self.assertEqual(payload["messages"][1]["sources"][0]["source_name"], "doc.pdf")

    def test_thread_endpoints_return_503_when_thread_memory_unavailable(self) -> None:
        fake_store = SimpleNamespace(
            enabled=False,
            health=lambda: {
                "enabled": False,
                "ready": False,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.get("/api/threads", params={"username": "alice"})

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"], "thread_memory_unavailable")

    def test_get_thread_messages_returns_404_when_thread_not_found(self) -> None:
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            get_thread_messages=lambda **_: None,
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.get(
                "/api/threads/missing/messages",
                params={"username": "alice"},
            )

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"], "thread_not_found")

    def test_rename_thread_success(self) -> None:
        now = datetime.now(timezone.utc)
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            rename_thread=lambda **_: {
                "thread_id": "thread-1",
                "title": "Renamed thread",
                "created_at": now,
                "updated_at": now,
                "message_count": 5,
                "last_message_preview": "latest",
            },
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.patch(
                "/api/threads/thread-1",
                json={"username": "alice", "title": "Renamed thread"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["thread"]["thread_id"], "thread-1")
        self.assertEqual(payload["thread"]["title"], "Renamed thread")

    def test_rename_thread_returns_404_when_missing(self) -> None:
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            rename_thread=lambda **_: None,
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.patch(
                "/api/threads/thread-missing",
                json={"username": "alice", "title": "Whatever"},
            )
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"], "thread_not_found")

    def test_delete_thread_success(self) -> None:
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            delete_thread=lambda **_: True,
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.delete(
                "/api/threads/thread-1",
                params={"username": "alice"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["deleted"])
        self.assertEqual(payload["thread_id"], "thread-1")

    def test_delete_thread_returns_404_when_missing(self) -> None:
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            delete_thread=lambda **_: False,
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            response = client.delete(
                "/api/threads/missing",
                params={"username": "alice"},
            )

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"], "thread_not_found")

    @patch("myMAT_app.api.server.answer_question_structured")
    def test_query_success(self, mock_answer_question_structured) -> None:
        mock_answer_question_structured.return_value = (
            StructuredRagAnswer(
                prompt="What is in the certificate?",
                bullets=["Certificate states migration compliance.", "Validity date is listed."],
                answer_text="The certificate confirms migration compliance and states validity details.",
            ),
            "- Certificate states migration compliance.\n- Validity date is listed.\n\nThe certificate confirms migration compliance and states validity details.",
            [
                Document(
                    page_content="context",
                    metadata={
                        "source": "/tmp/source.pdf",
                        "source_name": "source.pdf",
                        "doc_type": "Certifications",
                        "page_number": 1,
                    },
                )
            ],
        )

        response = self.client.post(
            "/api/rag/query",
            json={
                "question": "What is in the certificate?",
                "history": [{"role": "user", "content": "Earlier question"}],
                "retrieval": {
                    "k": 9,
                    "search_type": "mmr",
                    "fetch_k": 40,
                    "lambda_mult": 0.35,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("Certificate states migration compliance.", payload["answer"])
        self.assertEqual(payload["structured"]["prompt"], "What is in the certificate?")
        self.assertEqual(len(payload["structured"]["bullets"]), 2)
        self.assertEqual(payload["meta"]["k"], 9)
        self.assertEqual(payload["meta"]["search_type"], "mmr")
        self.assertEqual(payload["meta"]["chat_model"], "gpt-4.1-nano")
        self.assertEqual(len(payload["sources"]), 1)
        self.assertEqual(payload["sources"][0]["source_name"], "source.pdf")

    @patch("myMAT_app.api.server.answer_question_structured")
    def test_query_with_selected_chat_model(self, mock_answer_question_structured) -> None:
        mock_answer_question_structured.return_value = (
            StructuredRagAnswer(
                prompt="Classify this content",
                bullets=["Belongs to classification workflow."],
                answer_text="Category hint is available.",
            ),
            "- Belongs to classification workflow.\n\nCategory hint is available.",
            [],
        )
        response = self.client.post(
            "/api/rag/query",
            json={
                "question": "Classify this content",
                "chat_model": "qwen3.5:9b",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["chat_model"], "qwen3.5:9b")
        _, kwargs = mock_answer_question_structured.call_args
        self.assertEqual(kwargs["chat_model"], "qwen3.5:9b")

    def test_query_validation(self) -> None:
        response = self.client.post("/api/rag/query", json={"question": "   "})
        self.assertIn(response.status_code, {400, 422})

    def test_query_validation_invalid_chat_model(self) -> None:
        response = self.client.post(
            "/api/rag/query",
            json={"question": "Hello", "chat_model": "invalid-model"},
        )
        self.assertIn(response.status_code, {400, 422})

    @patch("myMAT_app.api.server.answer_question_structured")
    def test_query_backend_error(self, mock_answer_question_structured) -> None:
        mock_answer_question_structured.side_effect = RuntimeError("backend exploded")
        response = self.client.post(
            "/api/rag/query",
            json={"question": "Hello"},
        )
        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"], "backend_error")
        self.assertIn("backend exploded", payload["detail"]["message"])

    def test_query_uses_thread_memory_when_username_and_thread_id_are_provided(self) -> None:
        fake_store = SimpleNamespace(
            enabled=True,
            health=lambda: {
                "enabled": True,
                "ready": True,
                "db_name": "myMAT_threads",
                "last_error": None,
            },
            build_history=lambda **_: [{"role": "assistant", "content": "Previous response"}],
            persist_turn=lambda **_: True,
        )
        with patch("myMAT_app.api.server.create_thread_memory_store_from_env", return_value=fake_store):
            app = create_app()
            client = TestClient(app)
            with patch("myMAT_app.api.server.answer_question_structured") as mock_answer:
                mock_answer.return_value = (
                    StructuredRagAnswer(
                        prompt="Follow-up?",
                        bullets=["Uses memory."],
                        answer_text="Uses previous response context.",
                    ),
                    "- Uses memory.\n\nUses previous response context.",
                    [],
                )
                response = client.post(
                    "/api/rag/query",
                    json={
                        "question": "Follow-up?",
                        "username": "alice",
                        "thread_id": "thread-1",
                    },
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["meta"]["thread_memory_used"])
                self.assertTrue(payload["meta"]["thread_memory_ready"])
                self.assertEqual(payload["meta"]["thread_id"], "thread-1")
                _, kwargs = mock_answer.call_args
                self.assertEqual(
                    kwargs["history"],
                    [{"role": "assistant", "content": "Previous response"}],
                )


if __name__ == "__main__":
    unittest.main()
