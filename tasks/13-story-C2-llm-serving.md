# Task 13 — Story C2: OpenAI-compatible LLM serving
# Attach: 00-PROJECT-CONTEXT.md · AGENTS.md · docs/PRD.md (Epic C) · docs/ARCHITECTURE.md (§5, §6)
# Pre-req: C1 merged

Implement story C2: the platform serves a small local LLM through an
OpenAI-compatible API. Unmodified `openai` SDK clients must work by
swapping base_url + key.

Scope:
1. GPU node: Ollama installed as a service (document in docs/GPU-NODE.md:
   `curl -fsSL https://ollama.com/install.sh | sh`, `ollama pull
   llama3.2:3b` — fits 4GB VRAM quantized; bind OLLAMA_HOST to the
   Tailscale IP only). Settings gain OLLAMA_BASE_URL and LLM_MODEL_ID.
2. Proxy routes under `/api/v1/llm/v1/…` (mirror OpenAI paths so
   base_url=".../api/v1/llm/v1" just works):
   - `POST /chat/completions` — auth via API key with llm:invoke scope
     (or JWT); forward to Ollama's /v1/chat/completions (Ollama speaks
     the OpenAI dialect natively); force `model` to LLM_MODEL_ID
     regardless of client input (single-model platform, no surprises);
     support stream=true via httpx streaming passthrough (SSE), and
     stream=false.
   - `GET /models` — returns the one configured model, OpenAI list shape.
3. VRAM arbitration (the 4GB reality): before the worker starts a
   gpu=true JOB, it must ask Ollama to unload (`keep_alive: 0` request or
   /api/generate with keep_alive 0) and set a Redis flag
   `perzforge:gpu:training=1` (TTL = job timeout). The LLM proxy checks
   the flag: if set, return 503 with Retry-After and body explaining the
   GPU is training. Flag cleared on job end. Tests cover both directions.
4. Failure mapping: Ollama down → 502 with a clean error, never a stack
   trace; client disconnect mid-stream must cancel the upstream request
   (httpx aclose) — no orphaned generations.
5. Rate limiting: the E2 llm tier (20/min) now applies to these routes
   via the route→tier registry.
6. Smoke script `scripts/llm_smoke.py` using the official openai package
   against the platform, streaming and non-streaming.
7. Tests: mock Ollama with respx; scope enforcement; model override
   forced; streaming passthrough shape; 503-during-training; disconnect
   cancellation (best effort assertion).

Out of scope: token metering/budgets (C3), multiple models, GPU-aware
queueing beyond the mutual-exclusion flag, embeddings endpoint.

Commit message:
feat(C2): OpenAI-compatible LLM gateway with VRAM arbitration

The platform now fronts a local Ollama model behind faithful OpenAI
paths — unmodified SDK clients work by swapping base_url. Streaming
proxies cancel upstream on client disconnect, and a mutual-exclusion
flag arbitrates the 4GB GPU between inference and training so neither
workload can silently starve the other.
