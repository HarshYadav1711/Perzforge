# Task 02 — Story A3: Scoped API keys
# Attach: AGENTS.md · docs/PRD.md (Epic A) · docs/ARCHITECTURE.md (§7.1, §3)
# Pre-req: A2 merged (JWT auth live)

Implement story A3: users create/revoke named API keys for programmatic access.

Scope:
1. Model + migration: `ApiKey` — id, user_id FK, name, key_hash (SHA-256),
   prefix (first 8 chars of plaintext, for display: "pzf_a1b2…"), scopes
   (JSONB list), rate_limit_tier (text, default "standard"), expires_at
   nullable, revoked bool, last_used_at nullable, created_at.
2. Key format: `pzf_` + 32 url-safe random bytes (secrets.token_urlsafe).
   Store ONLY the SHA-256 hash. Return plaintext exactly once at creation
   with an explicit `"store_this_now"` field name that makes the contract obvious.
3. Routes (all require JWT auth via get_current_user):
   - `POST /api/v1/keys` — body: name, scopes (validate against the known
     scope set: jobs:read, jobs:write, models:read, llm:invoke,
     instances:manage), optional expires_at.
   - `GET /api/v1/keys` — caller's keys only; never any hash material,
     show prefix + metadata.
   - `DELETE /api/v1/keys/{id}` — ownership check (404 if not yours);
     sets revoked=true (soft revoke, keys are audit trail).
4. Auth extension in `api/deps.py`: `get_current_principal` accepts EITHER
   a JWT bearer OR an API key bearer (detect by `pzf_` prefix). API-key path:
   hash lookup, reject revoked/expired, enforce scopes via a
   `require_scopes("jobs:write")` dependency factory, update last_used_at
   (fire-and-forget, don't block the request).
5. Tests: creation returns plaintext once; list never leaks hashes; revoked
   key fails on the next request; scope enforcement (key without jobs:write
   gets 403 on a jobs:write route); expired key rejected; foreign key id → 404.

Out of scope: rate limit enforcement (E2 reads rate_limit_tier later), admin
key management, key rotation endpoints.

Touches auth — flag for human review.

Commit message:
feat(A3): scoped API keys with hashed storage and single-reveal issuance

Keys are pzf_-prefixed, SHA-256 hashed at rest, and carry per-key scopes
enforced by a reusable dependency. Dual-mode auth now accepts JWT sessions
or API keys through one principal resolver. Soft revocation preserves the
audit trail; plaintext is returned exactly once at creation.
