from __future__ import annotations

import re
from typing import Any

from myMAT_app.api.agents.common import FALLBACK_ESCALATION_TEXT, default_response
from myMAT_app.api.db.ops_store import MatOpsStore
from myMAT_app.api.tools import sql_tool


def _ticket_from_message(message: str) -> str | None:
    match = re.search(r"\bCMP-\d{8}-\d{4}\b", message.upper())
    return match.group(0) if match else None


def _severity_from_message(message: str) -> str:
    text = message.lower()
    if "critical" in text:
        return "critical"
    if "high" in text or "urgent" in text:
        return "high"
    if "low" in text:
        return "low"
    return "medium"


def run_complaints_agent(
    *,
    message: str,
    form_payload: dict[str, Any] | None,
    store: MatOpsStore,
) -> dict[str, Any]:
    payload = form_payload or {}

    ticket_no = str(payload.get("ticket_no") or "").strip() or _ticket_from_message(message)
    customer_name = str(payload.get("customer_name") or "").strip()
    title = str(payload.get("complaint_title") or "").strip()
    description = str(payload.get("complaint_description") or "").strip()
    severity = str(payload.get("severity") or "").strip() or _severity_from_message(message)
    order_no = str(payload.get("order_no") or "").strip() or None

    wants_status = any(term in message.lower() for term in ["status", "update", "ticket", "complaint"])

    if ticket_no and wants_status and not title and not description:
        try:
            complaint = sql_tool.get_complaint(store, ticket_no=ticket_no)
            if complaint is None:
                return default_response(
                    routed_agent="agent_complains_management",
                    answer_text="I could not find that complaint ticket. Please verify the ticket number.",
                    bullets=["Expected ticket format: CMP-YYYYMMDD-XXXX."],
                )
            escalation = complaint["status"] in {"escalated", "critical"}
            bullets = [
                f"Ticket: {complaint['ticket_no']}",
                f"Customer: {complaint['customer_name']}",
                f"Status: {complaint['status']}",
                f"Severity: {complaint['severity']}",
            ]
            if escalation:
                bullets.append("This complaint is escalated for priority handling.")
            return default_response(
                routed_agent="agent_complains_management",
                answer_text=f"Complaint {complaint['ticket_no']} is currently {complaint['status']}.",
                bullets=bullets,
            )
        except Exception:
            return default_response(
                routed_agent="agent_complains_management",
                answer_text=FALLBACK_ESCALATION_TEXT,
                bullets=[FALLBACK_ESCALATION_TEXT],
                fallback_used=True,
            )

    if customer_name and title and description:
        try:
            complaint = sql_tool.create_complaint(
                store,
                customer_name=customer_name,
                title=title,
                description=description,
                severity=severity,
                order_no=order_no,
            )
            escalated = complaint["status"] == "escalated"
            bullets = [
                f"Ticket created: {complaint['ticket_no']}",
                f"Customer: {complaint['customer_name']}",
                f"Severity: {complaint['severity']}",
                f"Status: {complaint['status']}",
            ]
            if escalated:
                bullets.append("Escalation has been triggered due to high severity.")
            return default_response(
                routed_agent="agent_complains_management",
                answer_text=f"Complaint {complaint['ticket_no']} has been registered.",
                bullets=bullets,
            )
        except Exception:
            return default_response(
                routed_agent="agent_complains_management",
                answer_text=FALLBACK_ESCALATION_TEXT,
                bullets=[FALLBACK_ESCALATION_TEXT],
                fallback_used=True,
            )

    return default_response(
        routed_agent="agent_complains_management",
        answer_text="Please provide complaint details to open a ticket or share a ticket number for status.",
        bullets=[
            "For new complaint: customer_name + title + description (+ severity).",
            "For status check: provide ticket number (CMP-YYYYMMDD-XXXX).",
        ],
    )
