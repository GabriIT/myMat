from __future__ import annotations

from typing import Any

FALLBACK_ESCALATION_TEXT = (
    "Thank you for the interests and commitment to our products. "
    "In order to be able to fully answer your concern and queries our sales will contact you in the next 2 hours."
)


def is_selection_query(message: str) -> bool:
    text = message.lower()
    selection_terms = [
        "material selection",
        "select material",
        "which polymer",
        "recommend material",
        "application",
        "requirements",
        "property",
        "properties",
        "tensile",
        "temperature",
        "flame",
        "chemical resistance",
    ]
    matches = sum(1 for term in selection_terms if term in text)
    return matches >= 2


def ask_for_clarification(message: str) -> bool:
    text = message.strip()
    if len(text) > 40:
        return False
    fuzzy = ["material", "metal", "polymer", "ht", "help", "advise"]
    return any(term in text.lower() for term in fuzzy)


def clipped_bullets(items: list[str], max_items: int = 5) -> list[str]:
    output: list[str] = []
    for item in items:
        clean = item.strip(" -")
        if not clean:
            continue
        output.append(clean)
        if len(output) >= max_items:
            break
    return output


def default_response(
    *,
    routed_agent: str,
    answer_text: str,
    bullets: list[str] | None = None,
    sources: list[dict[str, Any]] | None = None,
    follow_up_questions: list[str] | None = None,
    used_web_fallback: bool = False,
    handoff_trace: list[str] | None = None,
    fallback_used: bool = False,
) -> dict[str, Any]:
    return {
        "routed_agent": routed_agent,
        "answer_text": answer_text,
        "bullets": clipped_bullets(bullets or []),
        "sources": sources or [],
        "follow_up_questions": follow_up_questions or [],
        "used_web_fallback": used_web_fallback,
        "handoff_trace": handoff_trace or [],
        "fallback_used": fallback_used,
    }
