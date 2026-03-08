# Deployment Plan: `myMAT_app` to `http://154.12.245.254/agentic-mat` (Ubuntu 24.04)

## Summary
1. Prepare `myMAT_app` with a dedicated deployment bundle (Docker + proxy snippets + VPS scripts), adapted from the proven `myRAG_app` deploy stack.
2. Run a non-disruptive VPS discovery and compatibility check before any install/change.
3. Install only missing prerequisites (Node 20, PostgreSQL 15+, Nginx) with conflict-safe strategy.
4. Deploy `myMAT_app` on localhost-only ports and expose it under `/agentic-mat` via the currently safest reverse proxy path.
5. Keep Ollama available by configuration only (not enabled as default inference path).
6. Support two vector DB paths: VPS rebuild (primary) and copy current active DB (fallback).
7. Add a dedicated runbook file: `/home/gabri/apps/myMAT_app/VPS_gabri_deployment_agemtic-mat_README.md`.

## Important Changes / Additions to Interfaces
1. New deployment env interface in `myMAT_app/deploy/.env.vps`:
`MYMAT_DB_PATH`, `MYMAT_COLLECTION`, `MYMAT_ALLOWED_ORIGINS`, `MYMAT_THREADS_*`, `MYMAT_OPS_*`, `OPENAI_API_KEY`, `OLLAMA_URL`, `MYMAT_BASE_PATH`, `VITE_BASE_PATH`, `VITE_API_BASE_URL`.
2. New path contract for reverse proxy:
`/agentic-mat/api/* -> 127.0.0.1:18100/api/*` and `/agentic-mat/* -> 127.0.0.1:18101/*`.
3. New deployment script contracts under `myMAT_app/deploy/scripts/`:
`vps_precheck.sh`, `vps_bootstrap_ubuntu24.sh`, `deploy_compose.sh`, `build_vector_db_vps.sh`, `copy_vector_db_from_local.sh`, `rollback_vector_db.sh`.
4. UI config fix for deployment correctness:
remove stale `/RAG-mat/api` dev proxy rule and standardize on `VITE_BASE_PATH=/agentic-mat/`, `VITE_API_BASE_URL=/agentic-mat`.
5. Runtime service names/ports for coexistence with existing app:
`mymat-api` on `127.0.0.1:18100`, `mymat-ui` on `127.0.0.1:18101` (no public bind).

## Phase 1: Local Repo Preparation (before VPS actions)
1. Create `myMAT_app/deploy/` by adapting `myRAG_app/deploy/`:
`Dockerfile.api`, `Dockerfile.ui`, `docker-compose.yml`, proxy snippets (`nginx`, `caddy`, `apache`), scripts.
2. Rename all `myRAG_*` references to `myMAT_*` in deploy files.
3. Set base path defaults to `/agentic-mat`.
4. Configure compose volumes:
mount VPS vector DB to API container (`/data/vector_db`), add `extra_hosts: host.docker.internal:host-gateway` for optional Ollama host access.
5. Add `MYMAT_KNOWLEDGE_ROOT` env support in build-vector script for VPS rebuild workflow.
6. Add/update runbook file:
`/home/gabri/apps/myMAT_app/VPS_gabri_deployment_agemtic-mat_README.md`.

## Phase 2: VPS Discovery (non-disruptive baseline)
Run on VPS from `~` and save output to `/tmp/mymat_vps_discovery_<timestamp>.log`.
1. OS/repos/services/ports/container inventory:
`lsb_release -a`, `uname -a`, `systemctl list-units --type=service --state=running`, `ss -ltnp`, `docker ps`.
2. Runtime/package checks:
`node -v`, `npm -v`, `apt-cache policy nodejs`, `apt-cache rdepends --installed nodejs`.
3. PostgreSQL checks:
`psql --version`, `pg_lsclusters`, `apt-cache policy postgresql postgresql-15 postgresql-16`, `apt list --installed 'postgresql*'`.
4. Proxy checks:
`systemctl is-active nginx`, `systemctl is-active apache2`, `systemctl is-active caddy`, plus containerized proxy detection via `docker ps`.
5. Capture existing app health URLs before any change.

## Phase 3: Conditional Install Strategy (no impact to existing apps)
1. Node 20:
If host Node is missing or <20, install user-scoped Node 20 via `nvm` only; do not replace global Node used by other apps.
2. PostgreSQL 15+:
If >=15 exists, reuse; otherwise install PostgreSQL 16 side-by-side (no destructive upgrade/removal).
3. Nginx:
Install only if missing. If another proxy already owns 80/443, keep Nginx installed but stopped/disabled.
4. Use bootstrap script in dry-run first, then apply:
`bash myMAT_app/deploy/scripts/vps_bootstrap_ubuntu24.sh --dry-run`
then
`bash myMAT_app/deploy/scripts/vps_bootstrap_ubuntu24.sh`.

## Phase 4: Deployment Root and Env on VPS
1. Use separate root:
`/home/ubuntu/mymat-deploy`.
2. Expected structure:
`/home/ubuntu/mymat-deploy/myMAT_app`, `/home/ubuntu/mymat-deploy/myRAG_knowledge`, `/home/ubuntu/mymat-deploy/vector_db`.
3. Create `myMAT_app/deploy/.env.vps` with:
`MYMAT_DB_PATH=/home/ubuntu/mymat-deploy/vector_db`
`MYMAT_COLLECTION=myrag_docs_markdown`
`MYMAT_ALLOWED_ORIGINS=http://154.12.245.254`
`MYMAT_BASE_PATH=/agentic-mat`
`VITE_BASE_PATH=/agentic-mat/`
`VITE_API_BASE_URL=/agentic-mat`
`OLLAMA_URL=http://host.docker.internal:11434`
`MYMAT_THREADS_ENABLED=1`
`MYMAT_THREADS_DB_NAME=myMAT_ops`
`MYMAT_OPS_ENABLED=1`
`MYMAT_OPS_DB_NAME=myMAT_ops`
plus DB credentials and `OPENAI_API_KEY`.
4. Configure DB (`myMAT_ops`) and pgvector idempotently before app start.

## Phase 5: Reverse Proxy Integration (safe-first)
1. Proxy choice rule:
reuse active production proxy first; only enable Nginx as active proxy if no suitable proxy exists.
2. Add `/agentic-mat` scoped routes only:
no edits to unrelated routes/vhosts.
3. Route mapping:
`/agentic-mat/api/ -> 127.0.0.1:18100/api/`
`/agentic-mat/ -> 127.0.0.1:18101/`
and redirect `/agentic-mat` to `/agentic-mat/`.
4. Reload proxy (not full restart of unrelated stacks).

## Phase 6: App Deploy via Docker Compose
1. From VPS path `/home/ubuntu/mymat-deploy/myMAT_app/deploy`:
run deployment script to build and start `mymat-api` and `mymat-ui`.
2. Confirm local health:
`curl -s http://127.0.0.1:18100/api/health`
`curl -I http://127.0.0.1:18101/`.

## Phase 7: Vector Store Strategy
1. Primary (VPS rebuild):
run strict parse + upgrade flow against VPS knowledge:
`python -m myMAT_app.vector.upgrade_cli --knowledge-root /home/ubuntu/mymat-deploy/myRAG_knowledge --active-db-path /home/ubuntu/mymat-deploy/vector_db --collection myrag_docs_markdown --strict-parse --quiet-parser-warnings`
2. Validate:
`python -m myMAT_app.vector.inspect_cli --db-path /home/ubuntu/mymat-deploy/vector_db --collection myrag_docs_markdown --sample 3`.
3. Fallback (copy active DB):
use deployment script to rsync currently active local DB from `/home/gabri/apps/myMAT_app/vector_db` to VPS active path.
4. Rollback:
use `rollback_vector_db.sh` to promote last good backup and restart only `mymat-api`.

## Phase 8: Validation and Sign-off
1. Public checks:
`curl -s http://154.12.245.254/agentic-mat/api/health`
open `http://154.12.245.254/agentic-mat/`.
2. Functional checks:
login, thread list/load, each agent path, order/complaint forms, source rendering.
3. Non-regression checks:
verify previously running VPS apps still healthy on pre-captured endpoints.

## Test Cases and Scenarios
1. Node conflict case: existing app needs Node 18, deploy uses `nvm` Node 20 with no global replacement.
2. PostgreSQL reuse case: existing PG >=15 reused without cluster disruption.
3. Proxy coexistence case: `/agentic-mat` added while `/RAG-mat` and other routes stay unchanged.
4. VPS vector rebuild case: strict parse pass, vector count > 0.
5. Fallback copy case: rebuild blocked, rsync copy works, inspect count > 0.
6. Rollback case: bad candidate reverted to previous vector DB.
7. Ollama availability case: `OLLAMA_URL` configured and reachable but not default-selected unless user chooses.
8. Thread memory readiness case: `/api/health` shows thread/ops backend ready and no 503 on thread APIs.

## `VPS_gabri_deployment_agemtic-mat_README.md` Content Plan
1. Exact local path and VPS path for each command.
2. Precheck matrix and interpretation.
3. Conditional install commands and “do-not-break-existing-apps” rules.
4. Docker deploy commands.
5. Reverse proxy snippets for Nginx/Caddy/Apache at `/agentic-mat`.
6. Vector rebuild/copy/rollback procedures.
7. Final smoke checklist and rollback checklist.

## Assumptions and Defaults
1. Final route is `/agentic-mat` (not `/materials`).
2. VPS deploy root is `/home/ubuntu/mymat-deploy`.
3. Vector collection default remains `myrag_docs_markdown` for compatibility with copied active DB.
4. Thread memory and ops use dedicated DB `myMAT_ops` on PostgreSQL 15+.
5. Docker Compose is available (or installable) and remains preferred runtime.
6. Ollama is configured as optional endpoint only; OpenAI remains default unless model selection changes at runtime.
