# myMAT Agentic Design

## Orchestrator
- Module: `myMAT_app/api/orchestrator.py`
- Entry endpoint: `POST /api/mat/query`
- Routing inputs:
  - `message`
  - `selected_agent_hint`
  - `history`
  - `form_payload`
- Button hint is strong; orchestrator overrides only for high-confidence mismatch intents.

## Agents

### Agent 1: Material Queries
- RAG-first (`myMAT_app/api/tools/rag_tool.py`)
- If low confidence, web fallback (max 5 bullets)
- Delegates to Agent 2 on selection-with-properties intent

### Agent 2: Polymer Specialist
- RAG-first with polymer-focused response style
- Web fallback (max 5 bullets) if RAG is weak

### Agent 3: Customer Service
- Handles quote/confirm/ETA
- Applies pricing policy:
  - `quantity_tons > 10` => 3% discount
- Delivery policy baseline:
  - 4-6 weeks from confirmation

### Agent 4: Complains Management
- Complaint intake
- Ticket status lookup
- Escalates high/critical severity

## Global fallback text
When unresolved:

> Thank you for the interests and commitment to our products. In order to be able to fully answer your concern and queries our sales will contact you in the next 2 hours.

## Persistence
- Threads: PostgreSQL via thread memory store
- Business data: PostgreSQL via ops store (`catalog`, `sales`, `crm`)

## UI behavior
- 4 top buttons select agent hint
- Sidebar/history from backend thread endpoints
- Agent 3 form for customer service context
- Agent 4 form for complaint context
