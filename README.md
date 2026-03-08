# myMAT_app

Multi-agent MVP (LangGraph orchestrator) for materials Q&A + customer service + complaints.

## What is implemented
- 4 agents routed by orchestrator (`/api/mat/query`):
  - `agent_material_queries`
  - `agent_polymer_specialist`
  - `agent_customer_service`
  - `agent_complains_management`
- RAG for Agent 1/2 via Chroma vectorstore.
- Web fallback (DuckDuckGo HTML scraping) for Agent 1/2 when RAG is weak.
- PostgreSQL-backed thread history endpoints.
- PostgreSQL ops backend for catalogs, orders, complaints.
- UI with:
  - 4 agent buttons
  - customer/material dropdowns
  - order form (Agent 3)
  - complaint form (Agent 4)
  - form-driven send (Customer Service / Complaints can submit without typing a prompt)
  - past-order dropdown auto-fill for Customer Service (order number, material, qty, price)

## 1. Environment
From repo root:

```bash
cd /home/gabri/apps/myMAT_app
cp .env.example .env
```

Edit `.env` with real credentials (`OPENAI_API_KEY`, DB credentials).

## 2. Sync active vectorstore from myRAG_app

```bash
bash scripts/sync_vectorstore_from_myrag.sh \
  /home/gabri/udemy/llm_engineering/myRAG_app/vector_db_markdown \
  /home/gabri/apps/myMAT_app/vector_db
```

## 3. Install dependencies

```bash
# Python deps (using your existing venv)
/home/gabri/udemy/llm_engineering/.venv/bin/python -m pip install -r requirements.txt

# UI deps
cd /home/gabri/apps/myMAT_app/myMAT_app/ui
npm install
```

## 4. Initialize DB schemas + seed mock data

```bash
cd /home/gabri/apps/myMAT_app
/home/gabri/udemy/llm_engineering/.venv/bin/python -m myMAT_app.api.init_db --json
/home/gabri/udemy/llm_engineering/.venv/bin/python scripts/seed_mock_data.py --reset --seed 42 --json
```

If you get `password authentication failed for user "postgresql"`:

```bash
sudo -u postgres psql -d postgres -c "ALTER ROLE postgresql WITH PASSWORD 'postgresql';"
PGPASSWORD=postgresql psql -h 127.0.0.1 -p 5432 -U postgresql -d myMAT_ops -c "SELECT current_user, current_database();"
```

Then rerun init + seed commands.

Expected seeded minimum:
- customers: `10`
- materials: `40`
- orders: `30`

## 5. Run backend

```bash
cd /home/gabri/apps/myMAT_app
/home/gabri/udemy/llm_engineering/.venv/bin/uvicorn myMAT_app.api.server:app --host 0.0.0.0 --port 8010 --env-file .env
```

## 6. Run frontend

```bash
cd /home/gabri/apps/myMAT_app/myMAT_app/ui
echo "VITE_API_BASE_URL=http://127.0.0.1:8010" > .env.local
npm run dev
```

Open the Vite URL.

## Key APIs
- `POST /api/mat/query`
- `GET /api/catalog/customers`
- `GET /api/catalog/materials`
- `POST /api/orders/quote`
- `POST /api/orders/confirm`
- `GET /api/orders`
- `POST /api/complaints`
- `GET /api/complaints/{ticket_no}`
- Thread APIs:
  - `GET /api/threads`
  - `POST /api/threads`
  - `GET /api/threads/{thread_id}/messages`
  - `PATCH /api/threads/{thread_id}`
  - `DELETE /api/threads/{thread_id}`

## Notes
- Orchestrator uses LangGraph if installed; otherwise fallback routing logic is used.
- Agent unresolved-case escalation text is enforced in agent logic.
- Keep Ollama available by setting `OLLAMA_URL`; model can be selected from UI.
