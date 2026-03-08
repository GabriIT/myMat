# VPS Deployment Runbook - myMAT_app (`/agentic-mat`)

Target:
- URL: `http://154.12.245.254/agentic-mat`
- OS: Ubuntu 24.04
- Deploy root: `/home/ubuntu/mymat-deploy`

This runbook is secret-safe:
- Never paste `OPENAI_API_KEY` in shell history output.
- Keep secrets only in `deploy/.env.vps` with `chmod 600`.

## 1. Upload/prepare code on VPS

```bash
cd /home/ubuntu
mkdir -p mymat-deploy
cd /home/ubuntu/mymat-deploy
# clone or rsync repo so this path exists:
# /home/ubuntu/mymat-deploy/myMAT_app
# /home/ubuntu/mymat-deploy/myRAG_knowledge
# /home/ubuntu/mymat-deploy/vector_db (optional at first)
```

## 2. Run non-disruptive VPS precheck

```bash
cd /home/ubuntu/mymat-deploy/myMAT_app
bash deploy/scripts/vps_precheck.sh \
  --knowledge-root /home/ubuntu/mymat-deploy/myRAG_knowledge \
  --vector-db-path /home/ubuntu/mymat-deploy/vector_db
```

Output log is written to `/tmp/mymat_vps_precheck_<timestamp>.log`.

## 3. Install missing prerequisites only

Dry-run first:

```bash
cd /home/ubuntu/mymat-deploy/myMAT_app
bash deploy/scripts/vps_bootstrap_ubuntu24.sh --dry-run
```

Apply:

```bash
cd /home/ubuntu/mymat-deploy/myMAT_app
bash deploy/scripts/vps_bootstrap_ubuntu24.sh
```

Behavior:
- Node 20: installed via user-scoped `nvm` if needed.
- PostgreSQL: reuses existing 15+; otherwise installs PG16 side-by-side.
- Nginx: installs only if missing; kept disabled if another proxy already owns 80/443.

## 4. Create deployment env file (secret-safe)

```bash
cd /home/ubuntu/mymat-deploy/myMAT_app/deploy
cp .env.example .env.vps
chmod 600 .env.vps
```

Edit `.env.vps` and set real values, especially:
- `OPENAI_API_KEY`
- `MYMAT_DB_PATH=/home/ubuntu/mymat-deploy/vector_db`
- `MYMAT_COLLECTION=myrag_docs_markdown`
- `MYMAT_ALLOWED_ORIGINS=http://154.12.245.254`
- `MYMAT_BASE_PATH=/agentic-mat`
- `VITE_BASE_PATH=/agentic-mat/`
- `VITE_API_BASE_URL=/agentic-mat`
- thread/ops DB credentials (`MYMAT_THREADS_*`, `MYMAT_OPS_*`)
- optional `OLLAMA_URL=http://host.docker.internal:11434`

## 5. Initialize PostgreSQL DB for thread + ops backend

Use your standard idempotent DB setup for `myMAT_ops` and pgvector, then run:

```bash
cd /home/ubuntu/mymat-deploy/myMAT_app
python3 -m myMAT_app.api.init_db --json
python3 scripts/seed_mock_data.py --reset --seed 42 --json
```

Expected: thread + ops ready and seeded counts shown.

## 6. Build/start Docker stack

```bash
cd /home/ubuntu/mymat-deploy/myMAT_app
bash deploy/scripts/deploy_compose.sh
```

Local container endpoints:
- API: `127.0.0.1:18100`
- UI: `127.0.0.1:18101`

## 7. Reverse proxy route at `/agentic-mat`

Reuse active proxy already serving VPS apps. Do not replace existing proxy unless needed.

### Nginx snippet
Use file: `deploy/nginx/location-agentic-mat.conf`

### Caddy snippet
Use file: `deploy/caddy/agentic-mat.caddy`

### Apache snippet
Use file: `deploy/apache/agentic-mat.conf`

After adding scoped route, reload the active proxy service.

## 8. Vector store workflow

## Path A (preferred): rebuild on VPS

```bash
cd /home/ubuntu/mymat-deploy/myMAT_app
bash deploy/scripts/build_vector_db_vps.sh \
  --knowledge-root /home/ubuntu/mymat-deploy/myRAG_knowledge \
  --active-db-path /home/ubuntu/mymat-deploy/vector_db \
  --collection myrag_docs_markdown
```

This runs:
1. strict parser audit
2. strict upgrade build (`--strict-parse --quiet-parser-warnings`)
3. inspect verification

## Path B (fallback): copy active local vector DB

Run from your local machine:

```bash
cd /home/gabri/apps/myMAT_app
bash deploy/scripts/copy_vector_db_from_local.sh \
  --remote-host 154.12.245.254 \
  --remote-user ubuntu \
  --remote-db-path /home/ubuntu/mymat-deploy/vector_db \
  --mode compose \
  --remote-repo-path /home/ubuntu/mymat-deploy/myMAT_app
```

## Rollback vector DB

On VPS:

```bash
cd /home/ubuntu/mymat-deploy/myMAT_app
bash deploy/scripts/rollback_vector_db.sh \
  --active-db-path /home/ubuntu/mymat-deploy/vector_db
```

## 9. Final checks

```bash
curl -s http://127.0.0.1:18100/api/health
curl -s http://154.12.245.254/agentic-mat/api/health
```

Open:
- `http://154.12.245.254/agentic-mat/`

Functional smoke:
- login
- thread list/history loads
- one query for each agent class
- sources displayed
- no thread-memory 503 (if DB enabled)

## 10. Safety checklist

- `.env.vps` exists and is mode `600`
- no secrets committed to git (`git status` clean, no `.env.vps` tracked)
- existing VPS apps are still healthy after proxy reload
- `/RAG-mat` and other routes remain unchanged
