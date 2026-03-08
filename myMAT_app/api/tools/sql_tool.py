from __future__ import annotations

from datetime import date
from typing import Any

from myMAT_app.api.db.ops_store import MatOpsStore


def list_customers(store: MatOpsStore) -> list[dict[str, Any]]:
    return store.list_customers()


def list_materials(store: MatOpsStore) -> list[dict[str, Any]]:
    return store.list_materials()


def quote_order(
    store: MatOpsStore,
    *,
    customer_name: str,
    material_name: str,
    quantity_tons: float,
    requested_delivery_time: date | None,
    explicit_price_cny_per_kg: float | None,
) -> dict[str, Any]:
    return store.compute_quote(
        customer_name=customer_name,
        material_name=material_name,
        quantity_tons=quantity_tons,
        requested_delivery_time=requested_delivery_time,
        explicit_price_cny_per_kg=explicit_price_cny_per_kg,
    )


def confirm_order(
    store: MatOpsStore,
    *,
    customer_name: str,
    material_name: str,
    quantity_tons: float,
    requested_delivery_time: date | None,
    explicit_price_cny_per_kg: float | None,
    contact_person: str | None,
    phone_number: str | None,
) -> dict[str, Any]:
    return store.confirm_order(
        customer_name=customer_name,
        material_name=material_name,
        quantity_tons=quantity_tons,
        requested_delivery_time=requested_delivery_time,
        explicit_price_cny_per_kg=explicit_price_cny_per_kg,
        contact_person=contact_person,
        phone_number=phone_number,
    )


def list_orders(
    store: MatOpsStore,
    *,
    customer_name: str | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return store.list_orders(customer_name=customer_name, limit=limit)


def create_complaint(
    store: MatOpsStore,
    *,
    customer_name: str,
    title: str,
    description: str,
    severity: str,
    order_no: str | None,
) -> dict[str, Any]:
    return store.create_complaint(
        customer_name=customer_name,
        title=title,
        description=description,
        severity=severity,
        order_no=order_no,
    )


def get_complaint(store: MatOpsStore, *, ticket_no: str) -> dict[str, Any] | None:
    return store.get_complaint(ticket_no=ticket_no)
