from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from myMAT_app.api.agents import (
    FALLBACK_ESCALATION_TEXT,
    run_complaints_agent,
    run_customer_service_agent,
    run_material_queries_agent,
    run_polymer_specialist_agent,
)
from myMAT_app.api.agents.common import is_selection_query
from myMAT_app.api.db.ops_store import MatOpsStore
from myMAT_app.vector.config import DEFAULT_CHAT_MODEL

AgentRoute = Literal[
    "agent_material_queries",
    "agent_polymer_specialist",
    "agent_customer_service",
    "agent_complains_management",
]


class OrchestratorState(TypedDict, total=False):
    message: str
    selected_agent_hint: AgentRoute | None
    chat_model: str
    retrieval: dict[str, Any]
    form_payload: dict[str, Any]
    history: list[dict[str, str]]
    route: AgentRoute
    response: dict[str, Any]


@dataclass(slots=True)
class OrchestratorDeps:
    ops_store: MatOpsStore


def _detect_intent_route(message: str) -> AgentRoute:
    text = message.lower()
    customer_terms = ["order", "quote", "price", "delivery", "eta", "quantity", "confirm"]
    complaint_terms = ["complaint", "ticket", "issue", "problem", "defect", "return"]
    polymer_terms = ["polymer", "ppa", "pa", "ht", "selection", "properties", "grade"]

    if sum(1 for term in complaint_terms if term in text) >= 1:
        return "agent_complains_management"
    if sum(1 for term in customer_terms if term in text) >= 2:
        return "agent_customer_service"
    if sum(1 for term in polymer_terms if term in text) >= 2 or is_selection_query(message):
        return "agent_polymer_specialist"
    return "agent_material_queries"


def _route_with_hint(message: str, selected_hint: AgentRoute | None) -> AgentRoute:
    inferred = _detect_intent_route(message)
    if selected_hint is None:
        return inferred

    # Strong hint behavior: override only on high-confidence mismatch.
    if selected_hint == inferred:
        return selected_hint

    high_conf_override = {
        "agent_customer_service": ["order", "quote", "delivery", "eta", "confirm"],
        "agent_complains_management": ["complaint", "ticket", "defect", "claim"],
    }
    terms = high_conf_override.get(inferred, [])
    text = message.lower()
    if terms and sum(1 for term in terms if term in text) >= 2:
        return inferred

    return selected_hint


def _supervisor_node(state: OrchestratorState) -> OrchestratorState:
    route = _route_with_hint(state.get("message", ""), state.get("selected_agent_hint"))
    return {"route": route}


def _material_agent_node(state: OrchestratorState, deps: OrchestratorDeps) -> OrchestratorState:
    response = run_material_queries_agent(
        message=state["message"],
        history=state.get("history", []),
        chat_model=state.get("chat_model") or DEFAULT_CHAT_MODEL,
        retrieval=state.get("retrieval"),
    )
    handoff = response.get("handoff_trace") or []
    if any("agent_polymer_specialist" in step for step in handoff):
        delegated = run_polymer_specialist_agent(
            message=state["message"],
            history=state.get("history", []),
            chat_model=state.get("chat_model") or DEFAULT_CHAT_MODEL,
            retrieval=state.get("retrieval"),
        )
        delegated["handoff_trace"] = [*handoff, "agent_polymer_specialist completed"]
        response = delegated
    return {"response": response}


def _polymer_agent_node(state: OrchestratorState, deps: OrchestratorDeps) -> OrchestratorState:
    response = run_polymer_specialist_agent(
        message=state["message"],
        history=state.get("history", []),
        chat_model=state.get("chat_model") or DEFAULT_CHAT_MODEL,
        retrieval=state.get("retrieval"),
    )
    return {"response": response}


def _customer_service_node(state: OrchestratorState, deps: OrchestratorDeps) -> OrchestratorState:
    response = run_customer_service_agent(
        message=state["message"],
        form_payload=state.get("form_payload"),
        store=deps.ops_store,
    )
    return {"response": response}


def _complaints_node(state: OrchestratorState, deps: OrchestratorDeps) -> OrchestratorState:
    response = run_complaints_agent(
        message=state["message"],
        form_payload=state.get("form_payload"),
        store=deps.ops_store,
    )
    return {"response": response}


def _run_without_langgraph(state: OrchestratorState, deps: OrchestratorDeps) -> dict[str, Any]:
    route = _route_with_hint(state.get("message", ""), state.get("selected_agent_hint"))
    if route == "agent_polymer_specialist":
        out = _polymer_agent_node(state, deps)
    elif route == "agent_customer_service":
        out = _customer_service_node(state, deps)
    elif route == "agent_complains_management":
        out = _complaints_node(state, deps)
    else:
        out = _material_agent_node(state, deps)
    response = out.get("response") or {
        "routed_agent": route,
        "answer_text": FALLBACK_ESCALATION_TEXT,
        "bullets": [FALLBACK_ESCALATION_TEXT],
        "sources": [],
        "follow_up_questions": [],
        "used_web_fallback": False,
        "handoff_trace": [],
        "fallback_used": True,
    }
    response["routed_agent"] = response.get("routed_agent") or route
    return response


def run_orchestrator(
    *,
    deps: OrchestratorDeps,
    message: str,
    selected_agent_hint: AgentRoute | None,
    chat_model: str | None,
    retrieval: dict[str, Any] | None,
    form_payload: dict[str, Any] | None,
    history: list[dict[str, str]] | None,
) -> dict[str, Any]:
    state: OrchestratorState = {
        "message": message,
        "selected_agent_hint": selected_agent_hint,
        "chat_model": chat_model or DEFAULT_CHAT_MODEL,
        "retrieval": retrieval or {},
        "form_payload": form_payload or {},
        "history": history or [],
    }

    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return _run_without_langgraph(state, deps)

    graph = StateGraph(OrchestratorState)

    graph.add_node("supervisor_router", _supervisor_node)
    graph.add_node("agent_material_queries", lambda s: _material_agent_node(s, deps))
    graph.add_node("agent_polymer_specialist", lambda s: _polymer_agent_node(s, deps))
    graph.add_node("agent_customer_service", lambda s: _customer_service_node(s, deps))
    graph.add_node("agent_complains_management", lambda s: _complaints_node(s, deps))

    graph.set_entry_point("supervisor_router")

    def _route(state_data: OrchestratorState) -> str:
        return state_data.get("route", "agent_material_queries")

    graph.add_conditional_edges(
        "supervisor_router",
        _route,
        {
            "agent_material_queries": "agent_material_queries",
            "agent_polymer_specialist": "agent_polymer_specialist",
            "agent_customer_service": "agent_customer_service",
            "agent_complains_management": "agent_complains_management",
        },
    )

    graph.add_edge("agent_material_queries", END)
    graph.add_edge("agent_polymer_specialist", END)
    graph.add_edge("agent_customer_service", END)
    graph.add_edge("agent_complains_management", END)

    app = graph.compile()
    result = app.invoke(state)

    response = result.get("response") if isinstance(result, dict) else None
    if not isinstance(response, dict):
        return _run_without_langgraph(state, deps)
    return response
