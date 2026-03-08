from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from myMAT_app.api.db.ops_store import create_ops_store_from_env
from myMAT_app.api.orchestrator import OrchestratorDeps, run_orchestrator
from myMAT_app.api.schemas import (
    CatalogCustomersResponse,
    CatalogMaterialsResponse,
    ComplaintCreateRequest,
    ComplaintResponse,
    ConfirmOrderRequest,
    ConfirmOrderResponse,
    CreateThreadRequest,
    CreateThreadResponse,
    DeleteThreadResponse,
    GenericMessageResponse,
    GetThreadMessagesResponse,
    HealthResponse,
    ListThreadsResponse,
    MatQueryMeta,
    MatQueryRequest,
    MatQueryResponse,
    OrdersResponse,
    QueryMeta,
    QueryRequest,
    QueryResponse,
    QuoteRequest,
    QuoteResponse,
    RenameThreadRequest,
    RenameThreadResponse,
    RetrievalOptions,
    SeedMockRequest,
    SeedMockResponse,
    SourceRef,
    StructuredAnswer,
)
from myMAT_app.api.thread_memory import create_thread_memory_store_from_env
from myMAT_app.api.tools import sql_tool
from myMAT_app.vector.config import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
)

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _allowed_origins_from_env() -> list[str]:
    raw = os.getenv("MYMAT_ALLOWED_ORIGINS", os.getenv("MYRAG_ALLOWED_ORIGINS", ""))
    if not raw.strip():
        return DEFAULT_ALLOWED_ORIGINS
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or DEFAULT_ALLOWED_ORIGINS


def _thread_memory_unavailable(detail_message: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "thread_memory_unavailable",
            "message": detail_message,
        },
    )


def _ops_backend_unavailable(detail_message: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "ops_backend_unavailable",
            "message": detail_message,
        },
    )


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except Exception:
        return None


def _legacy_answer_from_structured(answer_text: str, bullets: list[str]) -> str:
    lines = [f"- {item}" for item in bullets]
    if answer_text:
        if lines:
            lines.append("")
        lines.append(answer_text)
    return "\n".join(lines).strip() or answer_text


def create_app() -> FastAPI:
    app = FastAPI(title="myMAT API", version="0.2.0")
    allowed_origins = _allowed_origins_from_env()
    thread_memory_store = create_thread_memory_store_from_env()
    ops_store = create_ops_store_from_env()
    orchestrator_deps = OrchestratorDeps(ops_store=ops_store)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _require_thread_memory_ready() -> None:
        memory_health = thread_memory_store.health()
        if not bool(memory_health.get("enabled", False)):
            raise _thread_memory_unavailable("Thread memory backend is disabled.")
        if not bool(memory_health.get("ready", False)):
            message = str(memory_health.get("last_error") or "Thread memory backend is not ready.")
            raise _thread_memory_unavailable(message)

    def _require_ops_ready() -> None:
        ops_health = ops_store.health()
        if not bool(ops_health.get("enabled", False)):
            raise _ops_backend_unavailable("myMAT ops backend is disabled.")
        if not bool(ops_health.get("ready", False)):
            message = str(ops_health.get("last_error") or "myMAT ops backend is not ready.")
            raise _ops_backend_unavailable(message)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        db_path = Path(os.getenv("MYMAT_DB_PATH", os.getenv("MYRAG_DB_PATH", str(DEFAULT_DB_PATH)))).expanduser().resolve()
        collection = os.getenv("MYMAT_COLLECTION", os.getenv("MYRAG_COLLECTION", DEFAULT_COLLECTION_NAME))
        memory_health = thread_memory_store.health()
        ops_health = ops_store.health()
        return HealthResponse(
            status="ok",
            collection=collection,
            db_path=str(db_path),
            thread_memory_enabled=bool(memory_health.get("enabled", False)),
            thread_memory_ready=bool(memory_health.get("ready", False)),
            threads_db=memory_health.get("db_name"),
            thread_memory_error=memory_health.get("last_error"),
            ops_db_enabled=bool(ops_health.get("enabled", False)),
            ops_db_ready=bool(ops_health.get("ready", False)),
            ops_db_name=ops_health.get("db_name"),
            ops_db_error=ops_health.get("last_error"),
        )

    # Thread endpoints (backend authoritative history)
    @app.get("/api/threads", response_model=ListThreadsResponse)
    def list_threads(
        username: str = Query(..., min_length=1),
        limit: int = Query(50, ge=1, le=200),
    ) -> ListThreadsResponse:
        clean_username = username.strip()
        if not clean_username:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_username", "message": "username must not be blank"},
            )
        _require_thread_memory_ready()
        try:
            threads = thread_memory_store.list_threads(username=clean_username, limit=limit)
        except RuntimeError as exc:
            raise _thread_memory_unavailable(str(exc)) from exc
        return ListThreadsResponse(threads=threads)

    @app.post("/api/threads", response_model=CreateThreadResponse)
    def create_thread(payload: CreateThreadRequest) -> CreateThreadResponse:
        clean_username = payload.username.strip()
        clean_thread_id = (payload.thread_id or "").strip() or str(uuid4())
        thread_title = (payload.title or "").strip() or "New Thread"
        if not clean_username:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_username", "message": "username must not be blank"},
            )
        _require_thread_memory_ready()
        try:
            thread = thread_memory_store.create_thread(
                username=clean_username,
                thread_id=clean_thread_id,
                title=thread_title,
            )
        except RuntimeError as exc:
            raise _thread_memory_unavailable(str(exc)) from exc
        return CreateThreadResponse(thread=thread)

    @app.get("/api/threads/{thread_id}/messages", response_model=GetThreadMessagesResponse)
    def get_thread_messages(
        thread_id: str,
        username: str = Query(..., min_length=1),
        limit: int = Query(500, ge=1, le=1000),
    ) -> GetThreadMessagesResponse:
        clean_username = username.strip()
        clean_thread_id = thread_id.strip()
        if not clean_username:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_username", "message": "username must not be blank"},
            )
        if not clean_thread_id:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_thread_id", "message": "thread_id must not be blank"},
            )
        _require_thread_memory_ready()
        try:
            result = thread_memory_store.get_thread_messages(
                username=clean_username,
                thread_id=clean_thread_id,
                limit=limit,
            )
        except RuntimeError as exc:
            raise _thread_memory_unavailable(str(exc)) from exc
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "thread_not_found",
                    "message": f"Thread '{clean_thread_id}' was not found for user '{clean_username}'.",
                },
            )
        return GetThreadMessagesResponse(thread=result["thread"], messages=result["messages"])

    @app.patch("/api/threads/{thread_id}", response_model=RenameThreadResponse)
    def rename_thread(thread_id: str, payload: RenameThreadRequest) -> RenameThreadResponse:
        clean_thread_id = thread_id.strip()
        clean_username = payload.username.strip()
        clean_title = payload.title.strip()
        if not clean_thread_id:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_thread_id", "message": "thread_id must not be blank"},
            )
        if not clean_username:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_username", "message": "username must not be blank"},
            )
        if not clean_title:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_title", "message": "title must not be blank"},
            )

        _require_thread_memory_ready()
        try:
            thread = thread_memory_store.rename_thread(
                username=clean_username,
                thread_id=clean_thread_id,
                title=clean_title,
            )
        except RuntimeError as exc:
            raise _thread_memory_unavailable(str(exc)) from exc
        if thread is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "thread_not_found",
                    "message": f"Thread '{clean_thread_id}' was not found for user '{clean_username}'.",
                },
            )
        return RenameThreadResponse(thread=thread)

    @app.delete("/api/threads/{thread_id}", response_model=DeleteThreadResponse)
    def delete_thread(thread_id: str, username: str = Query(..., min_length=1)) -> DeleteThreadResponse:
        clean_thread_id = thread_id.strip()
        clean_username = username.strip()
        if not clean_thread_id:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_thread_id", "message": "thread_id must not be blank"},
            )
        if not clean_username:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_username", "message": "username must not be blank"},
            )

        _require_thread_memory_ready()
        try:
            deleted = thread_memory_store.delete_thread(username=clean_username, thread_id=clean_thread_id)
        except RuntimeError as exc:
            raise _thread_memory_unavailable(str(exc)) from exc
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "thread_not_found",
                    "message": f"Thread '{clean_thread_id}' was not found for user '{clean_username}'.",
                },
            )
        return DeleteThreadResponse(deleted=True, thread_id=clean_thread_id)

    # Catalog / business endpoints
    @app.get("/api/catalog/customers", response_model=CatalogCustomersResponse)
    def get_customers() -> CatalogCustomersResponse:
        _require_ops_ready()
        try:
            customers = sql_tool.list_customers(ops_store)
        except Exception as exc:
            raise _ops_backend_unavailable(str(exc)) from exc
        return CatalogCustomersResponse(customers=customers)

    @app.get("/api/catalog/materials", response_model=CatalogMaterialsResponse)
    def get_materials() -> CatalogMaterialsResponse:
        _require_ops_ready()
        try:
            materials = sql_tool.list_materials(ops_store)
        except Exception as exc:
            raise _ops_backend_unavailable(str(exc)) from exc
        return CatalogMaterialsResponse(materials=materials)

    @app.post("/api/orders/quote", response_model=QuoteResponse)
    def create_quote(payload: QuoteRequest) -> QuoteResponse:
        _require_ops_ready()
        try:
            quote = sql_tool.quote_order(
                ops_store,
                customer_name=payload.customer_name,
                material_name=payload.material_name,
                quantity_tons=payload.quantity_tons,
                requested_delivery_time=_parse_iso_date(payload.requested_delivery_time),
                explicit_price_cny_per_kg=payload.price_cny_per_kg,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": "quote_failed", "message": str(exc)}) from exc
        return QuoteResponse(**quote)

    @app.post("/api/orders/confirm", response_model=ConfirmOrderResponse)
    def confirm_order(payload: ConfirmOrderRequest) -> ConfirmOrderResponse:
        _require_ops_ready()
        try:
            confirmed = sql_tool.confirm_order(
                ops_store,
                customer_name=payload.customer_name,
                material_name=payload.material_name,
                quantity_tons=payload.quantity_tons,
                requested_delivery_time=_parse_iso_date(payload.requested_delivery_time),
                explicit_price_cny_per_kg=payload.price_cny_per_kg,
                contact_person=payload.contact_person,
                phone_number=payload.phone_number,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": "confirm_failed", "message": str(exc)}) from exc
        return ConfirmOrderResponse(**confirmed)

    @app.get("/api/orders", response_model=OrdersResponse)
    def get_orders(
        customer_name: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> OrdersResponse:
        _require_ops_ready()
        try:
            orders = sql_tool.list_orders(ops_store, customer_name=customer_name, limit=limit)
        except Exception as exc:
            raise _ops_backend_unavailable(str(exc)) from exc
        return OrdersResponse(orders=orders)

    @app.post("/api/complaints", response_model=ComplaintResponse)
    def create_complaint(payload: ComplaintCreateRequest) -> ComplaintResponse:
        _require_ops_ready()
        try:
            created = sql_tool.create_complaint(
                ops_store,
                customer_name=payload.customer_name,
                title=payload.title,
                description=payload.description,
                severity=payload.severity,
                order_no=payload.order_no,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "complaint_create_failed", "message": str(exc)},
            ) from exc

        complaint = sql_tool.get_complaint(ops_store, ticket_no=created["ticket_no"])
        if complaint is None:
            raise HTTPException(
                status_code=500,
                detail={"error": "complaint_fetch_failed", "message": "Complaint created but cannot be read."},
            )
        return ComplaintResponse(**complaint)

    @app.get("/api/complaints/{ticket_no}", response_model=ComplaintResponse)
    def get_complaint(ticket_no: str) -> ComplaintResponse:
        _require_ops_ready()
        complaint = sql_tool.get_complaint(ops_store, ticket_no=ticket_no)
        if complaint is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "complaint_not_found", "message": f"Ticket '{ticket_no}' not found."},
            )
        return ComplaintResponse(**complaint)

    @app.post("/api/admin/seed-mock", response_model=SeedMockResponse)
    def seed_mock(payload: SeedMockRequest) -> SeedMockResponse:
        _require_ops_ready()
        counts = ops_store.seed_mock_data(reset=payload.reset, seed=payload.seed)
        return SeedMockResponse(**counts)

    def _run_mat_query(payload: MatQueryRequest) -> MatQueryResponse:
        started = time.perf_counter()
        retrieval = payload.retrieval or RetrievalOptions()

        username = (payload.username or "").strip()
        thread_id = (payload.thread_id or "").strip()

        client_history = [{"role": item.role, "content": item.content} for item in payload.history]
        thread_memory_used = False
        thread_memory_ready: bool | None = None
        history = list(client_history)

        if username and thread_id and thread_memory_store.enabled:
            memory_health = thread_memory_store.health()
            thread_memory_ready = bool(memory_health.get("ready", False))
            if thread_memory_ready:
                history = thread_memory_store.build_history(
                    username=username,
                    thread_id=thread_id,
                    question=payload.message,
                    fallback_history=client_history,
                )
                thread_memory_used = True

        answer = run_orchestrator(
            deps=orchestrator_deps,
            message=payload.message,
            selected_agent_hint=payload.selected_agent_hint,
            chat_model=payload.chat_model,
            retrieval=retrieval.model_dump(),
            form_payload=payload.form_payload.model_dump(exclude_none=True) if payload.form_payload else None,
            history=history,
        )

        sources = [SourceRef(**src) for src in answer.get("sources", [])]

        if thread_memory_used:
            assistant_metadata = {
                "chat_model": payload.chat_model or DEFAULT_CHAT_MODEL,
                "structured": {
                    "prompt": payload.message,
                    "bullets": answer.get("bullets", []),
                    "answer_text": answer.get("answer_text", ""),
                },
                "sources": [src.model_dump() for src in sources[:20]],
                "routed_agent": answer.get("routed_agent"),
            }
            thread_memory_store.persist_turn(
                username=username,
                thread_id=thread_id,
                question=payload.message,
                answer=_legacy_answer_from_structured(answer.get("answer_text", ""), answer.get("bullets", [])),
                assistant_metadata=assistant_metadata,
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return MatQueryResponse(
            routed_agent=answer.get("routed_agent", "agent_material_queries"),
            answer_text=answer.get("answer_text", ""),
            bullets=answer.get("bullets", []),
            sources=sources,
            follow_up_questions=answer.get("follow_up_questions", []),
            meta=MatQueryMeta(
                chat_model=payload.chat_model or DEFAULT_CHAT_MODEL,
                routed_agent=answer.get("routed_agent", "agent_material_queries"),
                elapsed_ms=elapsed_ms,
                used_web_fallback=bool(answer.get("used_web_fallback", False)),
                handoff_trace=list(answer.get("handoff_trace", [])),
                fallback_used=bool(answer.get("fallback_used", False)),
                thread_id=thread_id or None,
            ),
        )

    @app.post("/api/mat/query", response_model=MatQueryResponse)
    def mat_query(payload: MatQueryRequest) -> MatQueryResponse:
        try:
            return _run_mat_query(payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "backend_error", "message": str(exc)},
            ) from exc

    # Backward compatibility endpoint
    @app.post("/api/rag/query", response_model=QueryResponse)
    def query_rag(payload: QueryRequest) -> QueryResponse:
        mat_payload = MatQueryRequest(
            username=payload.username,
            thread_id=payload.thread_id,
            message=payload.question,
            selected_agent_hint="agent_material_queries",
            chat_model=payload.chat_model,
            form_payload=None,
            retrieval=payload.retrieval,
            history=payload.history,
        )
        mat_response = _run_mat_query(mat_payload)
        retrieval = payload.retrieval or RetrievalOptions()
        return QueryResponse(
            answer=_legacy_answer_from_structured(mat_response.answer_text, mat_response.bullets),
            structured=StructuredAnswer(
                prompt=payload.question,
                bullets=mat_response.bullets,
                answer_text=mat_response.answer_text,
            ),
            sources=mat_response.sources,
            meta=QueryMeta(
                chat_model=payload.chat_model or DEFAULT_CHAT_MODEL,
                embedding_model=DEFAULT_EMBEDDING_MODEL,
                k=retrieval.k,
                search_type=retrieval.search_type,
                elapsed_ms=mat_response.meta.elapsed_ms,
                thread_memory_used=True,
                thread_memory_ready=None,
                thread_id=payload.thread_id,
            ),
        )

    @app.get("/api/info", response_model=GenericMessageResponse)
    def info() -> GenericMessageResponse:
        return GenericMessageResponse(
            ok=True,
            message="myMAT API ready",
            data={"default_chat_model": DEFAULT_CHAT_MODEL},
        )

    return app


app = create_app()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run myMAT FastAPI server.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0).")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000).")
    parser.add_argument("--reload", action="store_true", help="Enable autoreload for development.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    uvicorn.run("myMAT_app.api.server:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
