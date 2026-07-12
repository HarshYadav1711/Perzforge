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

## Status
- [x] Phase 0 — GPU node online (WSL2 interim)
- [ ] Phase 1 — auth + job runner  ← in progress
- [ ] Phase 2 — registry, MLflow, dashboard
- [ ] Phase 3 — serving (models + LLM)
- [ ] Phase 3.5 — compute instances
- [ ] Phase 4 — multi-node, monitoring, polish
