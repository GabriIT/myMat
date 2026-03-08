from __future__ import annotations

from typing import Any

from myMAT_app.api.agents.common import (
    FALLBACK_ESCALATION_TEXT,
    ask_for_clarification,
    default_response,
    is_selection_query,
)
from myMAT_app.api.tools.rag_tool import rag_answer
from myMAT_app.api.tools.web_search_tool import search_web_bullets


def run_material_queries_agent(
    *,
    message: str,
    history: list[dict[str, str]],
    chat_model: str,
    retrieval: dict[str, Any] | None,
    allow_web_fallback: bool = True,
) -> dict[str, Any]:
    if ask_for_clarification(message):
        return default_response(
            routed_agent="agent_material_queries",
            answer_text="Please provide target application, operating temperature range, and key constraints.",
            bullets=[
                "Tell me the target part/application.",
                "List required properties (mechanical/thermal/chemical/electrical).",
                "Share constraints such as cost, compliance, and process.",
            ],
            follow_up_questions=[
                "What is the application and operating environment?",
                "Which properties are mandatory versus preferred?",
            ],
        )

    if is_selection_query(message):
        return default_response(
            routed_agent="agent_material_queries",
            answer_text="Delegating to Polymer Specialist for property-based material selection.",
            bullets=["Handoff triggered to Agent 2 due to selection-style request with property constraints."],
            handoff_trace=["agent_material_queries -> agent_polymer_specialist"],
        )

    rag = rag_answer(
        question=message,
        history=history,
        chat_model=chat_model,
        retrieval=retrieval,
    )

    if rag["confidence"] != "low":
        return default_response(
            routed_agent="agent_material_queries",
            answer_text=rag["structured"]["answer_text"] or rag["answer"],
            bullets=rag["structured"]["bullets"],
            sources=rag["sources"],
        )

    if allow_web_fallback:
        try:
            web = search_web_bullets(message, max_items=5)
            return default_response(
                routed_agent="agent_material_queries",
                answer_text="RAG context was limited. Web fallback highlights are provided.",
                bullets=web["bullets"],
                sources=web["sources"],
                used_web_fallback=True,
            )
        except Exception:
            pass

    return default_response(
        routed_agent="agent_material_queries",
        answer_text=FALLBACK_ESCALATION_TEXT,
        bullets=[FALLBACK_ESCALATION_TEXT],
        fallback_used=True,
    )
