# myMAT_app MVP Plan: Multi-Agent Orchestrated Materials Assistant

## Summary
1. Build a new standalone app at `/home/gabri/apps/myMAT_app` by forking/adapting the current `myRAG_app` architecture.
2. Implement a LangGraph orchestrator that routes to 4 specialized agents with “button as strong hint” behavior.
3. Reuse RAG knowledge by copying the current active vector store (`myRAG_app/vector_db_markdown`) into `myMAT_app`.
4. Add a new PostgreSQL + pgvector database for broader scope (thread memory + orders + complaints + catalogs) using one DB with multiple schemas.
5. Add deterministic seeders for exactly 10 customers, 40 materials, 30 orders.
6. Build a single-workspace UI with 4 agent buttons, customer/material dropdowns, and Agent 3 order form.
7. Enforce response policies: web-fallback answers max 5 bullets; unresolved cases return your exact escalation text.

## Grounded Current State (from repo inspection)
1. `myMAT_app` exists and is empty: `/home/gabri/apps/myMAT_app`.
2. Current active local RAG env points to markdown vector DB:
`MYRAG_DB_PATH=/home/gabri/udemy/llm_engineering/myRAG_app/vector_db_markdown`
`MYRAG_COLLECTION=myrag_docs_markdown`.
3. Existing backend/frontend/thread-memory architecture is already solid and can be reused with rename/adaptation.
4. No existing web-search agent tooling is implemented yet in `myRAG_app`; this will be new in `myMAT_app`.

## Locked Decisions
1. Orchestrator framework: LangGraph router supervisor.
2. Agent 4 scope: intake + status + escalate.
3. Web fallback source: DuckDuckGo API-free approach.
4. DB layout: one new DB with multiple schemas.
5. Seed strategy: deterministic idempotent seeder script.
6. UI routing semantics: button is a strong hint, orchestrator can override.
7. Codebase strategy: fork/adapt into `/home/gabri/apps/myMAT_app`.
8. UI model: single workspace with agent buttons + contextual forms.

## Agent Behavior Specification
1. Agent 1 “Material Queries”.
It answers broad metals/high-performance materials questions using RAG first.
If RAG confidence is low, it uses web search and returns max 5 bullets.
If query is underspecified, it asks clarifying questions.
If query is a material-selection task with application + property requirements, it delegates to Agent 2.

2. Agent 2 “Polymer Specialist”.
Primary source is RAG.
If gaps remain, it uses web fallback and returns max 5 bullets.
It outputs candidate materials, tradeoffs, and confidence labels.

3. Agent 3 “Customer Service”.
It handles:
order acceptance/confirmation, ETA for confirmed orders, quantity/price queries.
Order form fields:
customer_name, contact_person, phone_number, material_name, quantity_tons, price_cny_per_kg, requested_delivery_time.
Delivery policy baseline:
4–6 weeks from confirmation.
Discount rule:
if quantity_tons > 10, apply 3% discount.

4. Agent 4 “Complaints Management”.
It handles:
new complaint intake, complaint status lookup, status updates, and escalation.
Escalation policy:
high severity or unresolved complaints trigger escalation state.

5. Global unresolved-case fallback text (exact):
“Thank you for the interests and commitment to our products. In order to be able to fully answer your concern and queries our sales will contact you in the next 2 hours.”

## Orchestrator Design (LangGraph)
1. Graph nodes:
`supervisor_router`, `agent_material_queries`, `agent_polymer_specialist`, `agent_customer_service`, `agent_complaints`.
2. Router inputs:
`user_message`, `selected_agent_hint`, `thread_context`, `structured_form_payload`.
3. Router logic:
apply button hint first, then override only when intent confidence is high for another agent.
4. Delegation rule:
Agent 1 calls handoff to Agent 2 when selection-intent is detected with explicit property constraints.
5. Tooling used by agent nodes:
RAG retrieval tool, DuckDuckGo search tool, SQL business-data tool.
6. Output contract (all agents):
`routed_agent`, `answer_text`, `bullets`, `sources`, `follow_up_questions`, `used_web_fallback`, `handoff_trace`, `fallback_used`.

## Public APIs / Interfaces / Types
1. `POST /api/mat/query`
Request:
`username`, `thread_id`, `message`, `selected_agent_hint`, `chat_model`, `form_payload`, `retrieval_options`.
Response:
`routed_agent`, `answer_text`, `bullets`, `sources`, `follow_up_questions`, `meta`.

2. `GET /api/catalog/customers`
Returns dropdown list for registered customers.

3. `GET /api/catalog/materials`
Returns dropdown list for available materials and base price.

4. `POST /api/orders/quote`
Computes quote with discount rule and lead-time estimate.

5. `POST /api/orders/confirm`
Creates/updates confirmed order record and promised delivery window.

6. `GET /api/orders`
Filterable order list for customer/order references and ETA checks.

7. `POST /api/complaints`
Creates complaint ticket and initial status.

8. `GET /api/complaints/{ticket_no}`
Returns complaint status/history.

9. Keep thread endpoints from current app pattern:
`GET /api/threads`, `POST /api/threads`, `GET /api/threads/{id}/messages`, `PATCH /api/threads/{id}`, `DELETE /api/threads/{id}`.

## Data Model / PostgreSQL + pgvector
1. New DB name default: `myMAT_ops`.
2. Schemas:
`memory`, `catalog`, `sales`, `crm`.
3. Tables:
`catalog.customers`, `catalog.materials`, `sales.orders`, `crm.complaints`, `crm.complaint_events`, `memory.thread_sessions`, `memory.thread_messages`.
4. Vector usage:
`memory.thread_messages.embedding vector(3072)` for semantic thread recall.
5. Indexing:
PK/FK indexes, order status/date indexes, complaint status/severity indexes, vector index where dimension constraints allow.
6. Idempotent migration/init scripts:
`api/init_db.py` and SQL migration files.

## Seeder Plan (Deterministic Mock Data)
1. `scripts/seed_mock_data.py` with `--reset` and `--seed` flags.
2. Generates exactly:
10 customers, 40 materials, 30 orders.
3. Orders include realistic spread:
mixed quantities, mixed statuses, pricing variation, discount cases (>10 tons).
4. Materials include:
high-performance polymers and relevant category/properties metadata.
5. Seeder is idempotent:
upsert-by-business-key, stable IDs, repeatable results.

## Vector Store Reuse Plan
1. Source copy:
`/home/gabri/udemy/llm_engineering/myRAG_app/vector_db_markdown`
2. Target in new app:
`/home/gabri/apps/myMAT_app/vector_db`.
3. New env defaults in `myMAT_app/.env`:
`MYMAT_DB_PATH=/home/gabri/apps/myMAT_app/vector_db`
`MYMAT_COLLECTION=myrag_docs_markdown`.
4. RAG wrapper in `myMAT_app` maps these envs to Chroma retriever.
5. Keep an optional `scripts/sync_vectorstore_from_myrag.sh` for refreshes.

## UI Plan (Single Workspace)
1. Top agent buttons:
“Agent Material Queries”, “Agent Polymer Specialist”, “Agent Customer Service”, “Agent Complains Management”.
2. Buttons set `selected_agent_hint`; orchestrator may override.
3. Keep thread sidebar/history pattern from current app.
4. Add dropdowns:
customers and materials (loaded from backend catalogs).
5. Agent 3 panel:
order form with required fields and submit actions for quote/confirm.
6. Agent 4 panel:
complaint intake fields and status lookup input.
7. Chat output:
bulleted answers and source list; web fallback capped at 5 bullets.
8. Error banner:
show fallback/escalation message when unresolved.

## Proposed File Structure (new app)
1. `myMAT_app/api/server.py`
2. `myMAT_app/api/schemas.py`
3. `myMAT_app/api/orchestrator.py`
4. `myMAT_app/api/agents/material_queries.py`
5. `myMAT_app/api/agents/polymer_specialist.py`
6. `myMAT_app/api/agents/customer_service.py`
7. `myMAT_app/api/agents/complaints.py`
8. `myMAT_app/api/tools/rag_tool.py`
9. `myMAT_app/api/tools/web_search_tool.py`
10. `myMAT_app/api/tools/sql_tool.py`
11. `myMAT_app/api/db/migrations/*.sql`
12. `myMAT_app/api/init_db.py`
13. `myMAT_app/scripts/seed_mock_data.py`
14. `myMAT_app/scripts/sync_vectorstore_from_myrag.sh`
15. `myMAT_app/ui/*` (forked from current `myRAG_app/ui` and adapted)
16. `myMAT_app/tests/*`
17. `myMAT_app/README.md`
18. `myMAT_app/README_setup_postgres.md`
19. `myMAT_app/README_agentic_design.md`

## Implementation Phases
1. Scaffold new project in `/home/gabri/apps/myMAT_app` and copy baseline backend/UI from `myRAG_app`.
2. Add env/config layer for `MYMAT_*` variables and preserve model selection support.
3. Implement DB migrations + init + deterministic seeder.
4. Copy vectorstore and wire RAG tool against copied DB.
5. Implement LangGraph orchestrator and 4 agent nodes with contracts.
6. Implement DuckDuckGo fallback tool and confidence-based trigger logic.
7. Implement catalog/orders/complaints APIs and integrate with Agent 3/4.
8. Adapt UI to agent buttons, forms, dropdowns, and orchestrated query endpoint.
9. Add tests and smoke scripts.
10. Document runbooks (local and deployment-ready).

## Test Cases and Scenarios
1. Routing tests:
button hint respected; override only on high-confidence mismatch.
2. Delegation tests:
Agent 1 handoff to Agent 2 on selection-style queries.
3. RAG/web fallback tests:
RAG-high-confidence path vs low-confidence web path.
4. Bullet policy tests:
web answers max 5 bullets.
5. Agent 3 pricing tests:
quantity 10 vs 10.01 tons; 3% discount applied only when >10.
6. ETA tests:
4–6 week policy reflected for confirmations.
7. Complaint lifecycle tests:
intake, status lookup, escalate transitions.
8. Fallback message tests:
exact text emitted when unresolved.
9. Seeder tests:
exact counts (10/40/30), idempotent reruns.
10. API integration tests:
`/api/mat/query`, catalog endpoints, order/complaint endpoints, thread endpoints.
11. UI tests:
agent button switching, dropdown load, order form submit, complaint status checks, source rendering.
12. End-to-end smoke:
register/login, run each agent flow, verify stored records and thread continuity.

## Acceptance Criteria
1. New app runs from `/home/gabri/apps/myMAT_app` independently.
2. Orchestrator routes among 4 specialized agents with traceable handoffs.
3. Agent 1 and 2 use copied RAG vectorstore by default.
4. Web fallback works for Agent 1/2 and returns max 5 bullets.
5. Agent 3 supports order acceptance, confirmation, ETA lookup, quantity pricing with discount rule.
6. Agent 4 supports complaint intake, status, and escalation.
7. UI has required agent-labeled buttons and customer/material dropdowns.
8. Mock dataset loads exactly 10 customers, 40 materials, 30 orders.
9. Unresolved cases return the exact fallback message string.
10. New PostgreSQL/pgvector DB supports thread memory + business workflows.

## Explicit Assumptions and Defaults
1. Currency label “Chinese Yen” is treated as CNY pricing in stored fields.
2. Delivery baseline is 4–6 weeks unless explicit rule overrides later.
3. Existing pseudo-auth pattern is retained for MVP.
4. Orchestrator stores thread memory in `memory` schema of `myMAT_ops`.
5. Vectorstore source of truth for MVP copy is current local `vector_db_markdown`.
6. Initial deployment target is local Ubuntu; deployment instructions will be included but not executed in this planning step.
