# Task 08 — Story E1: Quota engine
# Attach: AGENTS.md · docs/PRD.md (Epic E) · docs/ARCHITECTURE.md (§7.3)
# Pre-req: Epic B core merged

Implement story E1: per-user resource quotas enforced at the API.

Scope:
1. Model + migration: `Quota` — user_id PK/FK, max_concurrent_jobs (2),
   max_jobs_per_day (10), max_storage_mb (2048), max_instances (1),
   max_llm_tokens_per_day (50000). Defaults from settings; row created
   lazily on first check; admin route `PATCH /api/v1/admin/users/{id}/quota`
   to override per user.
2. `worker: quota.py` module → `api/quotas.py`: a single
   `enforce(user, resource, amount=1)` service consulted by handlers.
   Counting: concurrent jobs from Postgres (status in QUEUED/RUNNING/
   CANCELLING); daily counters in Redis with keys
   `perzforge:quota:{user}:{resource}:{yyyymmdd}` and 48h TTL (survives
   restarts, self-expires).
3. Replace B1's stopgap concurrency cap with the engine. Wire daily job
   count. Storage + instances + tokens consume it in their own stories —
   engine must support them now (resource is an enum).
4. Exceeding → 429 with body {"detail": "...", "quota": name,
   "limit": N, "current": M} — name the limit, per PRD E1.
5. `GET /api/v1/me/quota` — user sees limits + current usage.
6. Tests: default lazily created; over-concurrent blocked; daily counter
   increments/expires (freeze time or manipulate the key); admin override
   takes effect immediately; response body names the limit.

Out of scope: rate limiting (E2 — requests/min is different from quotas),
billing-style usage reports.

Touches quotas — flag for human review.

Commit message:
feat(E1): centralized quota engine with hybrid counting strategy

Resource ceilings are enforced through one service seam: authoritative
Postgres counts for live concurrency, self-expiring Redis counters for
daily windows. Rejections name the exhausted limit and current usage so
clients can self-diagnose. Admin overrides land per-user without redeploy.
