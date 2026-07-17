# Perzforge

Self-hosted mini-cloud & ML platform: GPU job scheduling, model registry,
LLM serving, and Linux compute instances — running on personal hardware,
accessible from anywhere via Tailscale.

## Docs
- [PRD](docs/PRD.md) — what & why, user stories, MVP definition
- [Architecture](docs/ARCHITECTURE.md) — components, data model, API, security
- [Phase 0 setup](docs/PHASE0-SETUP.md) — turning the hardware into a node
- [AGENTS.md](AGENTS.md) — rules for AI-assisted development

## Dev quickstart
```bash
cp .env.example .env          # fill in real values (openssl rand -hex 32 for JWT_SECRET)
docker compose up -d          # Postgres + Redis
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
# First admin (once): ADMIN_EMAIL=... ADMIN_PASSWORD=... python scripts/create_admin.py
uvicorn api.main:app --reload
curl localhost:8000/api/v1/healthz
pytest
```

## Dashboard (story F1)

Operator UI lives in `web/` (Next.js 15 App Router). Dev server proxies `/api/v1/*`
to FastAPI; live job logs open a WebSocket to the API (`NEXT_PUBLIC_WS_BASE`).

```bash
# API already running on :8000
cd web
cp .env.example .env.local    # adjust API_PROXY_TARGET / NEXT_PUBLIC_WS_BASE if needed
npm install
npm run dev                   # http://localhost:3000
```

Optional Compose service (does not start with default `compose up`):

```bash
docker compose --profile web up -d --build web
```

Frontend tests:

```bash
cd web
npm test                      # Vitest component tests
# Smoke (API + web running, real user):
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
E2E_EMAIL=you@example.com E2E_PASSWORD='your-password' \
npx playwright test
```

## Status
- [x] Phase 0 — GPU node online (WSL2 interim)
- [x] Phase 1 — auth + job runner + MVP dashboard (F1)
- [ ] Phase 2 — registry, MLflow
- [ ] Phase 3 — serving (models + LLM)
- [ ] Phase 3.5 — compute instances
- [ ] Phase 4 — multi-node, monitoring, polish
