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

CREATE TABLE IF NOT EXISTS crm.complaint_events (
  event_id BIGSERIAL PRIMARY KEY,
  ticket_no TEXT NOT NULL REFERENCES crm.complaints(ticket_no) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  note TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
