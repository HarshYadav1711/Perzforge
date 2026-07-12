# Task 09 — Story E2: Rate limiting
# Attach: AGENTS.md · docs/PRD.md (Epic E) · docs/ARCHITECTURE.md (§7.3)
# Pre-req: A3 merged (keys carry rate_limit_tier)

Implement story E2: fill the middleware stub with a Redis token bucket.

Scope:
1. `api/middleware.py`: token bucket as an atomic Lua script (EVALSHA,
   registered at startup via lifespan) — refill rate + burst per tier.
   Identity resolution order: API key prefix → user id from JWT → client IP
   (last resort). Fail-open ONLY on Redis outage, with a logged warning
   (availability over strictness for a self-hosted tool; document this
   decision in the summary).
2. Tiers in settings: default 60/min burst 90; auth routes 5/min per IP
   (login, refresh); jobs:write 10/hour; llm routes 20/min (consumed in C3).
   Route→tier mapping via a small registry, not hardcoded paths sprinkled
   around.
3. 429 responses: Retry-After + X-RateLimit-Limit/Remaining/Reset headers
   on every response (success too).
4. Exempt: /healthz. Nothing else.
5. Tests: burst then 429; headers correct; auth route stricter than
   general; identity isolation (two keys don't share a bucket); Lua
   atomicity under concurrent hits (asyncio.gather storm stays ≤ limit).

Touches security middleware — flag for human review.

Commit message:
feat(E2): atomic token-bucket rate limiting with tiered route policies

A Lua-scripted bucket makes check-and-decrement race-free under
concurrency, keyed by API key, session, or IP in that order. Route
policies live in one registry, auth endpoints get brute-force-grade
limits, and standard X-RateLimit headers make throttling observable to
well-behaved clients.
