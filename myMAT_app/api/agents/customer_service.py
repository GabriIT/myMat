from __future__ import annotations

import re
from datetime import date
from typing import Any

from myMAT_app.api.agents.common import FALLBACK_ESCALATION_TEXT, default_response
from myMAT_app.api.db.ops_store import MatOpsStore
from myMAT_app.api.tools import sql_tool


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _intent(message: str) -> str:
    text = message.lower()
    if any(term in text for term in ["confirm", "place order", "order now", "accept order"]):
        return "confirm"
    if any(term in text for term in ["eta", "delivery", "lead time", "status of order", "where is order"]):
        return "eta"
    if any(term in text for term in ["quote", "price", "cost", "quantity"]):
        return "quote"
    return "unknown"


def _extract_order_no(message: str) -> str | None:
    match = re.search(r"\bORD[-A-Z0-9]+\b", message.upper())
    return match.group(0) if match else None


def run_customer_service_agent(
    *,
    message: str,
    form_payload: dict[str, Any] | None,
    store: MatOpsStore,
) -> dict[str, Any]:
    payload = form_payload or {}
    intent = _intent(message)

    customer_name = str(payload.get("customer_name") or "").strip()
    material_name = str(payload.get("material_name") or "").strip()
    contact_person = str(payload.get("contact_person") or "").strip() or None
    phone_number = str(payload.get("phone_number") or "").strip() or None
    qty_raw = payload.get("quantity_tons")
    explicit_price = payload.get("price_cny_per_kg")
    requested_delivery = _parse_date(payload.get("requested_delivery_time"))

    quantity_tons: float | None
    try:
        quantity_tons = float(qty_raw) if qty_raw is not None and str(qty_raw).strip() else None
    except Exception:
        quantity_tons = None

    if intent == "eta":
        try:
            order_no = str(payload.get("order_no") or "").strip() or _extract_order_no(message)
            orders = sql_tool.list_orders(store, customer_name=customer_name or None, limit=20)
            if order_no:
                orders = [item for item in orders if item["order_no"].upper() == order_no.upper()]
            if not orders:
                return default_response(
                    routed_agent="agent_customer_service",
                    answer_text="I could not find the order yet. Please share order number or customer name.",
                    bullets=[
                        "Delivery policy baseline is 4 to 6 weeks from order confirmation.",
                        "Provide `order_no` (e.g., ORD-...) for exact ETA.",
                    ],
                    follow_up_questions=["What is the order number?", "Which customer placed the order?"],
                )
            top = orders[0]
            return default_response(
                routed_agent="agent_customer_service",
                answer_text=(
                    f"Order {top['order_no']} for {top['customer_name']} is currently {top['status']}. "
                    f"Promised window: {top['promised_delivery_from']} to {top['promised_delivery_to']}."
                ),
                bullets=[
                    f"Order: {top['order_no']}",
                    f"Status: {top['status']}",
                    f"Delivery window: {top['promised_delivery_from']} to {top['promised_delivery_to']}",
                    f"Material: {top['material_name']} ({top['quantity_tons']} tons)",
                ],
            )
        except Exception:
            return default_response(
                routed_agent="agent_customer_service",
                answer_text=FALLBACK_ESCALATION_TEXT,
                bullets=[FALLBACK_ESCALATION_TEXT],
                fallback_used=True,
            )

    if intent in {"quote", "confirm"}:
        if not customer_name or not material_name or quantity_tons is None:
            return default_response(
                routed_agent="agent_customer_service",
                answer_text="Please provide customer, material, and quantity to continue.",
                bullets=[
                    "Required: customer_name",
                    "Required: material_name",
                    "Required: quantity_tons",
                ],
                follow_up_questions=[
                    "Which customer is this for?",
                    "Which material grade is requested?",
                    "What quantity in tons is needed?",
                ],
            )

        try:
            if intent == "confirm":
                confirmed = sql_tool.confirm_order(
                    store,
                    customer_name=customer_name,
                    material_name=material_name,
                    quantity_tons=quantity_tons,
                    requested_delivery_time=requested_delivery,
                    explicit_price_cny_per_kg=float(explicit_price) if explicit_price not in (None, "") else None,
                    contact_person=contact_person,
                    phone_number=phone_number,
                )
                discount_text = (
                    "3% discount applied for quantity > 10 tons."
                    if confirmed["discount_pct"] > 0
                    else "No bulk discount applied (threshold is >10 tons)."
                )
                return default_response(
                    routed_agent="agent_customer_service",
                    answer_text=(
                        f"Order {confirmed['order_no']} confirmed for {confirmed['customer_name']}. "
                        f"Promised delivery window {confirmed['promised_delivery_from']} to {confirmed['promised_delivery_to']}."
                    ),
                    bullets=[
                        f"Material: {confirmed['material_name']}",
                        f"Quantity: {confirmed['quantity_tons']} tons",
                        f"Final price: {confirmed['final_price_cny_per_kg']} CNY/kg",
                        discount_text,
                    ],
                )

            quote = sql_tool.quote_order(
                store,
                customer_name=customer_name,
                material_name=material_name,
                quantity_tons=quantity_tons,
                requested_delivery_time=requested_delivery,
                explicit_price_cny_per_kg=float(explicit_price) if explicit_price not in (None, "") else None,
            )
            discount_text = (
                "3% discount applied for quantity > 10 tons."
                if quote["discount_pct"] > 0
                else "No bulk discount applied (threshold is >10 tons)."
            )
            return default_response(
                routed_agent="agent_customer_service",
                answer_text=(
                    f"Quote prepared for {quote['customer_name']} on {quote['material_name']}. "
                    f"Estimated delivery window {quote['promised_delivery_from']} to {quote['promised_delivery_to']}."
                ),
                bullets=[
                    f"Base price: {quote['unit_price_cny_per_kg']} CNY/kg",
                    f"Final price: {quote['final_price_cny_per_kg']} CNY/kg",
                    f"Quantity: {quote['quantity_tons']} tons",
                    discount_text,
                ],
            )
        except Exception:
            return default_response(
                routed_agent="agent_customer_service",
                answer_text=FALLBACK_ESCALATION_TEXT,
                bullets=[FALLBACK_ESCALATION_TEXT],
                fallback_used=True,
            )

    return default_response(
        routed_agent="agent_customer_service",
        answer_text="I can handle quote, order confirmation, and ETA checks.",
        bullets=[
            "Submit customer/material/quantity to get a quote.",
            "Use confirm to create a confirmed order with 4-6 week baseline delivery.",
            "Ask ETA using order number or customer name.",
        ],
    )
