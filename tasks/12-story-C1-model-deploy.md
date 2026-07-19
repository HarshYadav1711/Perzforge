# Task 12 — Story C1: One-click model deployment
# Attach: 00-PROJECT-CONTEXT.md · AGENTS.md · docs/PRD.md (Epic C) · docs/ARCHITECTURE.md (§2, §4)
# Pre-req: B4 merged

Implement story C1: a registered model becomes a live inference endpoint.

Scope:
1. Model + migration: `Endpoint` — id, model_id FK, user_id, name, status
   enum STARTING/LIVE/STOPPED/FAILED, container_id nullable, route (slug,
   unique), created_at, stopped_at nullable.
2. Serving contract v1 (documented in docs/SERVING.md, created here):
   the model's artifact prefix must contain `serve.py` exposing
   `def predict(payload: dict) -> dict`. The platform runs it inside a
   standard runner image (build `docker/serve-runner.Dockerfile`:
   python:3.12-slim + fastapi + uvicorn + a loader that imports serve.py)
   with the artifact dir mounted read-only at /model. Keep it deliberately
   minimal — this is a contract, not a framework.
3. `POST /api/v1/models/{id}/deploy` (ownership; quota: max 1 live
   endpoint per user via E1 engine): download artifacts to a host dir,
   start runner container (hardening per B3 minus network: attach to a
   dedicated bridge network `perzforge-serving`, no GPU by default),
   register route, poll /healthz inside until LIVE or 60s → FAILED.
4. Inference routing: `POST /api/v1/endpoints/{route}/predict` — auth
   (llm/infer scope or JWT), ownership NOT required (endpoints are
   caller-shareable within the platform: any authenticated user may call;
   record caller in usage_log), proxy the JSON body to the runner via
   httpx with a 30s timeout, stream back the response.
5. `POST /api/v1/endpoints/{id}/stop` (ownership) → stop+remove container,
   STOPPED, release quota. Worker/API restart reconciliation: on API
   startup, mark endpoints whose containers are gone as FAILED.
6. Dashboard: Deploy button on model page; endpoints list with status,
   route, stop button, and a "try it" JSON console.
7. Tests: full deploy→predict→stop cycle with a trivial serve.py fixture;
   contract violation (missing serve.py) → FAILED with clear error;
   non-owner can predict but cannot stop (404); startup reconciliation.

Out of scope: autoscaling, GPU inference endpoints, canary/versioned
routing, public exposure.

Touches container execution — flag for human review.

Commit message:
feat(C1): registry-to-endpoint deployment with a minimal serving contract

Any registered model exposing predict() now deploys into a sandboxed
runner container behind a routed, authenticated inference API. Health-
gated startup, startup-time reconciliation of vanished containers, and
quota-capped concurrency keep the serving plane self-consistent on a
single node.
