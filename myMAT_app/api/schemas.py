from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from myMAT_app.vector.config import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RETRIEVAL_FETCH_K,
    DEFAULT_RETRIEVAL_K,
    DEFAULT_RETRIEVAL_LAMBDA_MULT,
    DEFAULT_RETRIEVAL_SEARCH_TYPE,
    SUPPORTED_CHAT_MODELS,
)

RoleType = Literal["user", "assistant"]
SearchType = Literal["similarity", "mmr"]
AgentHint = Literal[
    "agent_material_queries",
    "agent_polymer_specialist",
    "agent_customer_service",
    "agent_complains_management",
]


class HistoryMessage(BaseModel):
    role: RoleType
    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("content must not be blank")
        return content


class RetrievalOptions(BaseModel):
    k: int = Field(default=DEFAULT_RETRIEVAL_K, ge=1, le=50)
    search_type: SearchType = DEFAULT_RETRIEVAL_SEARCH_TYPE
    fetch_k: int = Field(default=DEFAULT_RETRIEVAL_FETCH_K, ge=1, le=200)
    lambda_mult: float = Field(default=DEFAULT_RETRIEVAL_LAMBDA_MULT, ge=0.0, le=1.0)
    doc_type: str | None = None
    source_contains: str | None = None


class SourceRef(BaseModel):
    source: str
    source_name: str
    doc_type: str
    page_number: int | None = None
    sheet_name: str | None = None


class StructuredAnswer(BaseModel):
    prompt: str
    bullets: list[str] = Field(default_factory=list)
    answer_text: str


class QueryMeta(BaseModel):
    chat_model: str = DEFAULT_CHAT_MODEL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    k: int
    search_type: SearchType
    elapsed_ms: int
    thread_memory_used: bool = False
    thread_memory_ready: bool | None = None
    thread_id: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[HistoryMessage] = Field(default_factory=list)
    retrieval: RetrievalOptions | None = None
    chat_model: str | None = None
    username: str | None = None
    thread_id: str | None = None

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("question must not be blank")
        return question

    @field_validator("chat_model")
    @classmethod
    def validate_chat_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        model = value.strip()
        if not model:
            return None
        if model not in SUPPORTED_CHAT_MODELS:
            raise ValueError(f"chat_model must be one of: {', '.join(SUPPORTED_CHAT_MODELS)}")
        return model

    @field_validator("username", "thread_id")
    @classmethod
    def validate_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        identifier = value.strip()
        return identifier or None


class QueryResponse(BaseModel):
    answer: str
    structured: StructuredAnswer | None = None
    sources: list[SourceRef]
    meta: QueryMeta


class MatFormPayload(BaseModel):
    customer_name: str | None = None
    contact_person: str | None = None
    phone_number: str | None = None
    material_name: str | None = None
    quantity_tons: float | None = None
    price_cny_per_kg: float | None = None
    requested_delivery_time: str | None = None
    order_no: str | None = None
    ticket_no: str | None = None
    complaint_title: str | None = None
    complaint_description: str | None = None
    severity: str | None = None


class MatQueryRequest(BaseModel):
    username: str | None = None
    thread_id: str | None = None
    message: str = Field(..., min_length=1)
    selected_agent_hint: AgentHint | None = None
    chat_model: str | None = None
    form_payload: MatFormPayload | None = None
    retrieval: RetrievalOptions | None = None
    history: list[HistoryMessage] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message must not be blank")
        return cleaned

    @field_validator("chat_model")
    @classmethod
    def validate_query_chat_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        model = value.strip()
        if not model:
            return None
        if model not in SUPPORTED_CHAT_MODELS:
            raise ValueError(f"chat_model must be one of: {', '.join(SUPPORTED_CHAT_MODELS)}")
        return model


class MatQueryMeta(BaseModel):
    chat_model: str
    routed_agent: AgentHint
    elapsed_ms: int
    used_web_fallback: bool = False
    handoff_trace: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    thread_id: str | None = None


class MatQueryResponse(BaseModel):
    routed_agent: AgentHint
    answer_text: str
    bullets: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    meta: MatQueryMeta


class CatalogCustomer(BaseModel):
    customer_name: str
    contact_person: str
    phone_number: str


class CatalogMaterial(BaseModel):
    material_name: str
    category: str
    base_price_cny_per_kg: float


class CatalogCustomersResponse(BaseModel):
    customers: list[CatalogCustomer] = Field(default_factory=list)


class CatalogMaterialsResponse(BaseModel):
    materials: list[CatalogMaterial] = Field(default_factory=list)


class QuoteRequest(BaseModel):
    customer_name: str = Field(..., min_length=1)
    material_name: str = Field(..., min_length=1)
    quantity_tons: float = Field(..., gt=0)
    price_cny_per_kg: float | None = Field(default=None, gt=0)
    requested_delivery_time: str | None = None


class QuoteResponse(BaseModel):
    customer_name: str
    material_name: str
    category: str
    quantity_tons: float
    unit_price_cny_per_kg: float
    discount_pct: float
    final_price_cny_per_kg: float
    requested_delivery_time: str | None = None
    promised_delivery_from: str
    promised_delivery_to: str


class ConfirmOrderRequest(QuoteRequest):
    contact_person: str | None = None
    phone_number: str | None = None


class ConfirmOrderResponse(QuoteResponse):
    order_id: int
    order_no: str
    status: str


class OrderItem(BaseModel):
    order_no: str
    customer_name: str
    material_name: str
    quantity_tons: float
    final_price_cny_per_kg: float
    status: str
    promised_delivery_from: str | None = None
    promised_delivery_to: str | None = None
    created_at: datetime


class OrdersResponse(BaseModel):
    orders: list[OrderItem] = Field(default_factory=list)


class ComplaintCreateRequest(BaseModel):
    customer_name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity: str = "medium"
    order_no: str | None = None


class ComplaintEvent(BaseModel):
    event_type: str
    note: str
    created_at: datetime


class ComplaintResponse(BaseModel):
    ticket_no: str
    customer_name: str
    severity: str
    status: str
    title: str
    description: str
    created_at: datetime
    updated_at: datetime | None = None
    events: list[ComplaintEvent] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    collection: str
    db_path: str
    thread_memory_enabled: bool = False
    thread_memory_ready: bool = False
    threads_db: str | None = None
    thread_memory_error: str | None = None
    ops_db_enabled: bool = False
    ops_db_ready: bool = False
    ops_db_name: str | None = None
    ops_db_error: str | None = None


class ThreadSummary(BaseModel):
    thread_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = Field(default=0, ge=0)
    last_message_preview: str | None = None


class ListThreadsResponse(BaseModel):
    threads: list[ThreadSummary] = Field(default_factory=list)


class CreateThreadRequest(BaseModel):
    username: str = Field(..., min_length=1)
    thread_id: str | None = None
    title: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username must not be blank")
        return username

    @field_validator("thread_id", "title")
    @classmethod
    def validate_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None


class CreateThreadResponse(BaseModel):
    thread: ThreadSummary


class RenameThreadRequest(BaseModel):
    username: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)

    @field_validator("username", "title")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned


class RenameThreadResponse(BaseModel):
    thread: ThreadSummary


class DeleteThreadResponse(BaseModel):
    deleted: bool = True
    thread_id: str


class ThreadMessageItem(BaseModel):
    id: int
    role: RoleType
    content: str
    created_at: datetime
    structured: StructuredAnswer | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    routed_agent: AgentHint | None = None


class GetThreadMessagesResponse(BaseModel):
    thread: ThreadSummary
    messages: list[ThreadMessageItem] = Field(default_factory=list)


class SeedMockRequest(BaseModel):
    reset: bool = False
    seed: int = 42


class SeedMockResponse(BaseModel):
    customers: int
    materials: int
    orders: int


class GenericMessageResponse(BaseModel):
    ok: bool = True
    message: str
    data: dict[str, Any] | None = None
