# PostgreSQL Setup for myMAT_app

This setup creates one DB (`myMAT_ops`) used for:
- thread memory (pgvector)
- catalog/orders/complaints data

## Prerequisites
- PostgreSQL 15+
- `pgvector` extension package installed for your PostgreSQL major

## 1. Create role/db (idempotent)

```bash
sudo -u postgres psql <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgresql') THEN
    CREATE ROLE postgresql LOGIN PASSWORD 'postgresql';
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'myMAT_ops') THEN
    CREATE DATABASE "myMAT_ops" OWNER postgresql;
  END IF;
END $$;
SQL
```

## 2. Enable extension as superuser

```bash
sudo -u postgres psql -d myMAT_ops -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## 3. Initialize app schemas

```bash
cd /home/gabri/apps/myMAT_app
/home/gabri/udemy/llm_engineering/.venv/bin/python -m myMAT_app.api.init_db --json
```

## 4. Seed deterministic mock data

```bash
cd /home/gabri/apps/myMAT_app
/home/gabri/udemy/llm_engineering/.venv/bin/python scripts/seed_mock_data.py --reset --seed 42 --json
```

## 5. Health check

```bash
curl -s http://127.0.0.1:8010/api/health | jq .
```

You should see `thread_memory_enabled=true`, `thread_memory_ready=true`, `ops_db_ready=true` when `.env` is configured correctly.
