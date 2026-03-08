from __future__ import annotations

from typing import Any

from myMAT_app.api.agents.common import FALLBACK_ESCALATION_TEXT, default_response
from myMAT_app.api.tools.rag_tool import rag_answer
from myMAT_app.api.tools.web_search_tool import search_web_bullets


def _tradeoff_bullets(base_bullets: list[str]) -> list[str]:
    extras = [
        "Trade-off: higher heat resistance grades usually increase cost and mold-temperature requirements.",
        "Trade-off: glass-fiber reinforcement improves stiffness but can reduce impact toughness.",
    ]
    merged = [*base_bullets]
    for item in extras:
        if len(merged) >= 5:
            break
        merged.append(item)
    return merged[:5]


def run_polymer_specialist_agent(
    *,
    message: str,
    history: list[dict[str, str]],
    chat_model: str,
    retrieval: dict[str, Any] | None,
    allow_web_fallback: bool = True,
) -> dict[str, Any]:
    rag = rag_answer(
        question=message,
        history=history,
        chat_model=chat_model,
        retrieval=retrieval,
    )

    if rag["confidence"] != "low":
        bullets = _tradeoff_bullets(rag["structured"]["bullets"])
        return default_response(
            routed_agent="agent_polymer_specialist",
            answer_text=rag["structured"]["answer_text"] or rag["answer"],
            bullets=bullets,
            sources=rag["sources"],
        )

    if allow_web_fallback:
        try:
            web = search_web_bullets(f"high performance polymer {message}", max_items=5)
            return default_response(
                routed_agent="agent_polymer_specialist",
                answer_text="RAG context was limited. Web fallback highlights are provided.",
                bullets=web["bullets"],
                sources=web["sources"],
                used_web_fallback=True,
            )
        except Exception:
            pass

    return default_response(
        routed_agent="agent_polymer_specialist",
        answer_text=FALLBACK_ESCALATION_TEXT,
        bullets=[FALLBACK_ESCALATION_TEXT],
        fallback_used=True,
    )
