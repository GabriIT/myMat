from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from dotenv import load_dotenv

try:
    import psycopg
except Exception:  # pragma: no cover - runtime dependency
    psycopg = None


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_first(names: tuple[str, ...], default: str) -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return default


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class MatOpsDbConfig:
    enabled: bool
    dsn: str | None
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str
    connect_timeout: int

    @classmethod
    def from_env(cls) -> "MatOpsDbConfig":
        load_dotenv(override=False)
        dsn_raw = _env_first(("MYMAT_OPS_DB_DSN",), "")
        return cls(
            enabled=_bool_env("MYMAT_OPS_ENABLED", True),
            dsn=dsn_raw or None,
            host=_env_first(("MYMAT_OPS_DB_HOST", "MYMAT_THREADS_DB_HOST", "MYRAG_THREADS_DB_HOST"), "127.0.0.1"),
            port=_int_env(
                "MYMAT_OPS_DB_PORT",
                _int_env("MYMAT_THREADS_DB_PORT", _int_env("MYRAG_THREADS_DB_PORT", 5432, 1, 65535), 1, 65535),
                1,
                65535,
            ),
            dbname=_env_first(("MYMAT_OPS_DB_NAME", "MYMAT_THREADS_DB_NAME", "MYRAG_THREADS_DB_NAME"), "myMAT_ops"),
            user=_env_first(("MYMAT_OPS_DB_USER", "MYMAT_THREADS_DB_USER", "MYRAG_THREADS_DB_USER"), "postgresql"),
            password=_env_first(("MYMAT_OPS_DB_PASSWORD", "MYMAT_THREADS_DB_PASSWORD", "MYRAG_THREADS_DB_PASSWORD"), "postgresql"),
            sslmode=_env_first(("MYMAT_OPS_DB_SSLMODE",), "disable"),
            connect_timeout=_int_env("MYMAT_OPS_DB_CONNECT_TIMEOUT", 5, 1, 60),
        )


class MatOpsStore:
    def __init__(self, config: MatOpsDbConfig):
        self.config = config
        self._initialized = False
        self._init_error: str | None = None

    def _build_dsn(self) -> str:
        if self.config.dsn:
            return self.config.dsn
        return (
            f"host={self.config.host} "
            f"port={self.config.port} "
            f"dbname={self.config.dbname} "
            f"user={self.config.user} "
            f"password={self.config.password} "
            f"sslmode={self.config.sslmode} "
            f"connect_timeout={self.config.connect_timeout}"
        )

    def _connect(self):
        if psycopg is None:
            raise RuntimeError(
                "psycopg is not installed. Install with: uv pip install --python .venv/bin/python psycopg[binary]"
            )
        return psycopg.connect(self._build_dsn(), autocommit=True)

    def ensure_schema(self) -> bool:
        if not self.config.enabled:
            return False
        if self._initialized:
            return True

        schema_sql = """
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE SCHEMA IF NOT EXISTS memory;
        CREATE SCHEMA IF NOT EXISTS catalog;
        CREATE SCHEMA IF NOT EXISTS sales;
        CREATE SCHEMA IF NOT EXISTS crm;

        CREATE TABLE IF NOT EXISTS memory.thread_sessions (
          username TEXT NOT NULL,
          thread_id TEXT NOT NULL,
          title TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (username, thread_id)
        );

        CREATE TABLE IF NOT EXISTS memory.thread_messages (
          id BIGSERIAL PRIMARY KEY,
          username TEXT NOT NULL,
          thread_id TEXT NOT NULL,
          role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
          content TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          embedding vector(3072),
          metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT fk_memory_thread_session
            FOREIGN KEY (username, thread_id)
            REFERENCES memory.thread_sessions (username, thread_id)
            ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_memory_thread_messages_lookup
          ON memory.thread_messages (username, thread_id, created_at, id);

        CREATE TABLE IF NOT EXISTS catalog.customers (
          customer_id BIGSERIAL PRIMARY KEY,
          customer_code TEXT NOT NULL UNIQUE,
          customer_name TEXT NOT NULL UNIQUE,
          contact_person TEXT NOT NULL,
          phone_number TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS catalog.materials (
          material_id BIGSERIAL PRIMARY KEY,
          material_code TEXT NOT NULL UNIQUE,
          material_name TEXT NOT NULL UNIQUE,
          category TEXT NOT NULL,
          base_price_cny_per_kg NUMERIC(12,2) NOT NULL,
          properties JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS sales.orders (
          order_id BIGSERIAL PRIMARY KEY,
          order_no TEXT NOT NULL UNIQUE,
          customer_id BIGINT NOT NULL REFERENCES catalog.customers(customer_id),
          material_id BIGINT NOT NULL REFERENCES catalog.materials(material_id),
          quantity_tons NUMERIC(12,3) NOT NULL CHECK (quantity_tons > 0),
          unit_price_cny_per_kg NUMERIC(12,2) NOT NULL,
          discount_pct NUMERIC(5,2) NOT NULL DEFAULT 0,
          final_price_cny_per_kg NUMERIC(12,2) NOT NULL,
          requested_delivery_date DATE,
          promised_delivery_from DATE,
          promised_delivery_to DATE,
          status TEXT NOT NULL DEFAULT 'confirmed',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          confirmed_at TIMESTAMPTZ
        );

        CREATE INDEX IF NOT EXISTS idx_sales_orders_customer
          ON sales.orders (customer_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sales_orders_status
          ON sales.orders (status, promised_delivery_to);

        CREATE TABLE IF NOT EXISTS crm.complaints (
          ticket_no TEXT PRIMARY KEY,
          customer_id BIGINT NOT NULL REFERENCES catalog.customers(customer_id),
          order_id BIGINT REFERENCES sales.orders(order_id),
          severity TEXT NOT NULL DEFAULT 'medium',
          status TEXT NOT NULL DEFAULT 'open',
          title TEXT NOT NULL,
          description TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_crm_complaints_status
          ON crm.complaints (status, severity, updated_at DESC);

        CREATE TABLE IF NOT EXISTS crm.complaint_events (
          event_id BIGSERIAL PRIMARY KEY,
          ticket_no TEXT NOT NULL REFERENCES crm.complaints(ticket_no) ON DELETE CASCADE,
          event_type TEXT NOT NULL,
          note TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_crm_complaint_events_ticket
          ON crm.complaint_events (ticket_no, created_at DESC);
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
            self._initialized = True
            self._init_error = None
            return True
        except Exception as exc:  # pragma: no cover - depends on local db state
            self._init_error = str(exc)
            return False

    def health(self) -> dict[str, Any]:
        ready = self.ensure_schema()
        return {
            "enabled": self.config.enabled,
            "ready": ready,
            "db_name": self.config.dbname,
            "last_error": self._init_error,
        }

    def _require_ready(self) -> None:
        if not self.ensure_schema():
            raise RuntimeError(self._init_error or "myMAT ops DB is not ready")

    def list_customers(self) -> list[dict[str, Any]]:
        self._require_ready()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT customer_name, contact_person, phone_number
                    FROM catalog.customers
                    ORDER BY customer_name ASC
                    """
                )
                rows = cur.fetchall()
        return [
            {
                "customer_name": str(row[0]),
                "contact_person": str(row[1]),
                "phone_number": str(row[2]),
            }
            for row in rows
        ]

    def list_materials(self) -> list[dict[str, Any]]:
        self._require_ready()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT material_name, category, base_price_cny_per_kg
                    FROM catalog.materials
                    ORDER BY material_name ASC
                    """
                )
                rows = cur.fetchall()
        return [
            {
                "material_name": str(row[0]),
                "category": str(row[1]),
                "base_price_cny_per_kg": float(row[2]),
            }
            for row in rows
        ]

    def _find_customer_id(self, conn, customer_name: str) -> int | None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT customer_id FROM catalog.customers WHERE lower(customer_name)=lower(%s) LIMIT 1",
                (customer_name.strip(),),
            )
            row = cur.fetchone()
        return int(row[0]) if row else None

    def _find_material(self, conn, material_name: str) -> dict[str, Any] | None:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT material_id, material_name, category, base_price_cny_per_kg
                FROM catalog.materials
                WHERE lower(material_name)=lower(%s)
                LIMIT 1
                """,
                (material_name.strip(),),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "material_id": int(row[0]),
            "material_name": str(row[1]),
            "category": str(row[2]),
            "base_price": Decimal(row[3]),
        }

    @staticmethod
    def _delivery_window(requested: date | None = None) -> tuple[date, date]:
        base = requested or _now_utc().date()
        return (base + timedelta(weeks=4), base + timedelta(weeks=6))

    def compute_quote(
        self,
        *,
        customer_name: str,
        material_name: str,
        quantity_tons: float,
        requested_delivery_time: date | None = None,
        explicit_price_cny_per_kg: float | None = None,
    ) -> dict[str, Any]:
        self._require_ready()
        qty = Decimal(str(quantity_tons))
        if qty <= 0:
            raise ValueError("quantity_tons must be > 0")

        with self._connect() as conn:
            material = self._find_material(conn, material_name)
            if material is None:
                raise ValueError(f"Unknown material '{material_name}'")

        base_price = Decimal(str(explicit_price_cny_per_kg)) if explicit_price_cny_per_kg else material["base_price"]
        discount_pct = Decimal("3.0") if qty > Decimal("10") else Decimal("0")
        multiplier = Decimal("1") - (discount_pct / Decimal("100"))
        final_price = _quantize_money(base_price * multiplier)
        delivery_from, delivery_to = self._delivery_window(requested_delivery_time)

        return {
            "customer_name": customer_name.strip(),
            "material_name": material["material_name"],
            "category": material["category"],
            "quantity_tons": float(qty),
            "unit_price_cny_per_kg": float(_quantize_money(base_price)),
            "discount_pct": float(discount_pct),
            "final_price_cny_per_kg": float(final_price),
            "requested_delivery_time": requested_delivery_time.isoformat() if requested_delivery_time else None,
            "promised_delivery_from": delivery_from.isoformat(),
            "promised_delivery_to": delivery_to.isoformat(),
        }

    def confirm_order(
        self,
        *,
        customer_name: str,
        material_name: str,
        quantity_tons: float,
        requested_delivery_time: date | None,
        explicit_price_cny_per_kg: float | None = None,
        contact_person: str | None = None,
        phone_number: str | None = None,
    ) -> dict[str, Any]:
        self._require_ready()
        quote = self.compute_quote(
            customer_name=customer_name,
            material_name=material_name,
            quantity_tons=quantity_tons,
            requested_delivery_time=requested_delivery_time,
            explicit_price_cny_per_kg=explicit_price_cny_per_kg,
        )

        created = _now_utc()
        order_no = f"ORD-{created.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

        with self._connect() as conn:
            customer_id = self._find_customer_id(conn, customer_name)
            if customer_id is None:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO catalog.customers (customer_code, customer_name, contact_person, phone_number)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (customer_name) DO UPDATE SET
                          contact_person = EXCLUDED.contact_person,
                          phone_number = EXCLUDED.phone_number
                        RETURNING customer_id
                        """,
                        (
                            f"CUS-{abs(hash(customer_name)) % 100000:05d}",
                            customer_name.strip(),
                            (contact_person or "Unknown").strip() or "Unknown",
                            (phone_number or "Unknown").strip() or "Unknown",
                        ),
                    )
                    row = cur.fetchone()
                customer_id = int(row[0])

            material = self._find_material(conn, material_name)
            if material is None:
                raise ValueError(f"Unknown material '{material_name}'")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sales.orders (
                      order_no,
                      customer_id,
                      material_id,
                      quantity_tons,
                      unit_price_cny_per_kg,
                      discount_pct,
                      final_price_cny_per_kg,
                      requested_delivery_date,
                      promised_delivery_from,
                      promised_delivery_to,
                      status,
                      confirmed_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',now())
                    RETURNING order_id
                    """,
                    (
                        order_no,
                        customer_id,
                        material["material_id"],
                        quote["quantity_tons"],
                        quote["unit_price_cny_per_kg"],
                        quote["discount_pct"],
                        quote["final_price_cny_per_kg"],
                        quote["requested_delivery_time"],
                        quote["promised_delivery_from"],
                        quote["promised_delivery_to"],
                    ),
                )
                order_id = int(cur.fetchone()[0])

        return {
            "order_id": order_id,
            "order_no": order_no,
            "status": "confirmed",
            **quote,
        }

    def list_orders(
        self,
        *,
        customer_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._require_ready()
        capped = max(1, min(200, int(limit)))
        where = ""
        params: list[Any] = []
        if customer_name and customer_name.strip():
            where = "WHERE lower(c.customer_name) = lower(%s)"
            params.append(customer_name.strip())

        query = f"""
            SELECT
              o.order_no,
              c.customer_name,
              m.material_name,
              o.quantity_tons,
              o.final_price_cny_per_kg,
              o.status,
              o.promised_delivery_from,
              o.promised_delivery_to,
              o.created_at
            FROM sales.orders o
            JOIN catalog.customers c ON c.customer_id = o.customer_id
            JOIN catalog.materials m ON m.material_id = o.material_id
            {where}
            ORDER BY o.created_at DESC
            LIMIT %s
        """
        params.append(capped)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()

        return [
            {
                "order_no": str(row[0]),
                "customer_name": str(row[1]),
                "material_name": str(row[2]),
                "quantity_tons": float(row[3]),
                "final_price_cny_per_kg": float(row[4]),
                "status": str(row[5]),
                "promised_delivery_from": row[6].isoformat() if row[6] else None,
                "promised_delivery_to": row[7].isoformat() if row[7] else None,
                "created_at": row[8],
            }
            for row in rows
        ]

    def create_complaint(
        self,
        *,
        customer_name: str,
        title: str,
        description: str,
        severity: str = "medium",
        order_no: str | None = None,
    ) -> dict[str, Any]:
        self._require_ready()
        severity_clean = severity.strip().lower() or "medium"
        if severity_clean not in {"low", "medium", "high", "critical"}:
            severity_clean = "medium"

        now = _now_utc()
        ticket_no = f"CMP-{now.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

        with self._connect() as conn:
            customer_id = self._find_customer_id(conn, customer_name)
            if customer_id is None:
                raise ValueError(f"Unknown customer '{customer_name}'")

            order_id: int | None = None
            if order_no and order_no.strip():
                with conn.cursor() as cur:
                    cur.execute("SELECT order_id FROM sales.orders WHERE order_no=%s LIMIT 1", (order_no.strip(),))
                    row = cur.fetchone()
                if row:
                    order_id = int(row[0])

            initial_status = "escalated" if severity_clean in {"high", "critical"} else "open"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO crm.complaints (
                      ticket_no, customer_id, order_id, severity, status, title, description
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        ticket_no,
                        customer_id,
                        order_id,
                        severity_clean,
                        initial_status,
                        title.strip(),
                        description.strip(),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO crm.complaint_events (ticket_no, event_type, note)
                    VALUES (%s,'created',%s)
                    """,
                    (ticket_no, "Complaint ticket created."),
                )

        return {
            "ticket_no": ticket_no,
            "customer_name": customer_name.strip(),
            "severity": severity_clean,
            "status": initial_status,
            "title": title.strip(),
            "description": description.strip(),
            "created_at": now,
        }

    def get_complaint(self, *, ticket_no: str) -> dict[str, Any] | None:
        self._require_ready()
        ticket = ticket_no.strip()
        if not ticket:
            return None

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      c.ticket_no,
                      cu.customer_name,
                      c.severity,
                      c.status,
                      c.title,
                      c.description,
                      c.created_at,
                      c.updated_at
                    FROM crm.complaints c
                    JOIN catalog.customers cu ON cu.customer_id = c.customer_id
                    WHERE c.ticket_no = %s
                    LIMIT 1
                    """,
                    (ticket,),
                )
                row = cur.fetchone()
                if row is None:
                    return None

                cur.execute(
                    """
                    SELECT event_type, note, created_at
                    FROM crm.complaint_events
                    WHERE ticket_no = %s
                    ORDER BY created_at ASC, event_id ASC
                    """,
                    (ticket,),
                )
                events = cur.fetchall()

        return {
            "ticket_no": str(row[0]),
            "customer_name": str(row[1]),
            "severity": str(row[2]),
            "status": str(row[3]),
            "title": str(row[4]),
            "description": str(row[5]),
            "created_at": row[6],
            "updated_at": row[7],
            "events": [
                {
                    "event_type": str(evt[0]),
                    "note": str(evt[1]),
                    "created_at": evt[2],
                }
                for evt in events
            ],
        }

    def seed_mock_data(self, *, reset: bool = False, seed: int = 42) -> dict[str, int]:
        self._require_ready()
        rng = random.Random(seed)

        customer_names = [
            "Apex Mobility",
            "BlueRiver Components",
            "Crown Dynamics",
            "Delta Precision",
            "EverSpark Electronics",
            "FutureMotion Auto",
            "Golden Axis Tech",
            "Horizon Powertrain",
            "Ionix Systems",
            "Jade Industrial",
        ]

        materials: list[tuple[str, str, float]] = []
        categories = ["HT", "PA", "PPA", "PPS", "Metal Replacement"]
        for idx in range(1, 41):
            code = f"MAT-{idx:03d}"
            category = categories[(idx - 1) % len(categories)]
            name = f"{category} Grade {idx:02d}"
            price = round(18 + (idx * 1.35), 2)
            materials.append((code, name, price))

        with self._connect() as conn:
            with conn.cursor() as cur:
                if reset:
                    cur.execute("TRUNCATE crm.complaint_events, crm.complaints, sales.orders RESTART IDENTITY CASCADE")
                    cur.execute("TRUNCATE catalog.customers, catalog.materials RESTART IDENTITY CASCADE")

                for idx, name in enumerate(customer_names, start=1):
                    cur.execute(
                        """
                        INSERT INTO catalog.customers (customer_code, customer_name, contact_person, phone_number)
                        VALUES (%s,%s,%s,%s)
                        ON CONFLICT (customer_name) DO UPDATE SET
                          contact_person = EXCLUDED.contact_person,
                          phone_number = EXCLUDED.phone_number
                        """,
                        (
                            f"CUS-{idx:03d}",
                            name,
                            f"Contact {idx}",
                            f"+86-21-4000-{idx:04d}",
                        ),
                    )

                for code, name, price in materials:
                    cur.execute(
                        """
                        INSERT INTO catalog.materials (
                          material_code, material_name, category, base_price_cny_per_kg, properties
                        ) VALUES (%s,%s,%s,%s,%s::jsonb)
                        ON CONFLICT (material_name) DO UPDATE SET
                          category = EXCLUDED.category,
                          base_price_cny_per_kg = EXCLUDED.base_price_cny_per_kg,
                          properties = EXCLUDED.properties
                        """,
                        (
                            code,
                            name,
                            name.split()[0],
                            price,
                            '{"heat_resistance":"high","application":"automotive/electronics"}',
                        ),
                    )

                cur.execute("SELECT customer_id FROM catalog.customers ORDER BY customer_id")
                customer_ids = [int(row[0]) for row in cur.fetchall()]
                cur.execute("SELECT material_id, base_price_cny_per_kg FROM catalog.materials ORDER BY material_id")
                mat_rows = [(int(row[0]), Decimal(row[1])) for row in cur.fetchall()]

                order_today = _now_utc().date()
                for idx in range(1, 31):
                    customer_id = rng.choice(customer_ids)
                    material_id, base_price = rng.choice(mat_rows)
                    qty = Decimal(str(round(rng.uniform(1.5, 18.0), 3)))
                    discount = Decimal("3.0") if qty > Decimal("10") else Decimal("0")
                    final_price = _quantize_money(base_price * (Decimal("1") - discount / Decimal("100")))
                    created_days_ago = rng.randint(0, 90)
                    created_at = order_today - timedelta(days=created_days_ago)
                    delivery_from = created_at + timedelta(weeks=4)
                    delivery_to = created_at + timedelta(weeks=6)
                    status = rng.choice(["confirmed", "in_production", "shipped", "delivered"])
                    cur.execute(
                        """
                        INSERT INTO sales.orders (
                          order_no, customer_id, material_id, quantity_tons,
                          unit_price_cny_per_kg, discount_pct, final_price_cny_per_kg,
                          requested_delivery_date, promised_delivery_from, promised_delivery_to,
                          status, created_at, confirmed_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (order_no) DO NOTHING
                        """,
                        (
                            f"ORD-SEED-{idx:03d}",
                            customer_id,
                            material_id,
                            float(qty),
                            float(base_price),
                            float(discount),
                            float(final_price),
                            created_at,
                            delivery_from,
                            delivery_to,
                            status,
                            datetime.combine(created_at, datetime.min.time(), tzinfo=timezone.utc),
                            datetime.combine(created_at, datetime.min.time(), tzinfo=timezone.utc),
                        ),
                    )

                cur.execute("SELECT count(*) FROM catalog.customers")
                customers_count = int(cur.fetchone()[0])
                cur.execute("SELECT count(*) FROM catalog.materials")
                materials_count = int(cur.fetchone()[0])
                cur.execute("SELECT count(*) FROM sales.orders")
                orders_count = int(cur.fetchone()[0])

        return {
            "customers": customers_count,
            "materials": materials_count,
            "orders": orders_count,
        }


def create_ops_store_from_env() -> MatOpsStore:
    return MatOpsStore(MatOpsDbConfig.from_env())
