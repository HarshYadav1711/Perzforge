# Cursor task — Story A2: Login & session security

Paste this into Cursor/Codex as the task. Attach `AGENTS.md`, `docs/PRD.md`
(Epic A), and `docs/ARCHITECTURE.md` (§3 data model, §7.1 auth) as context.

---

Implement user story **A2** from docs/PRD.md:

> As a user, I can log in and stay logged in securely.
> ✅ JWT access (15 min) + rotating refresh token in httpOnly cookie;
> refresh reuse revokes the token family.

Scope:
1. `api/models.py`: add `User` (id, email unique, password_hash, role enum
   [admin|user|readonly], must_change_password bool, created_at) and
   `RefreshToken` (id, user_id FK, token_hash, family_id, expires_at,
   revoked bool, created_at). Alembic migration included.
2. `api/security.py` (new): Argon2id hash/verify; JWT encode/decode
   (HS256, secret from settings, 15-min expiry, `sub`=user_id, `role` claim).
3. `api/routers/auth.py` (new):
   - `POST /api/v1/auth/login` — email+password (Pydantic, extra="forbid").
     Success: JWT in JSON body + refresh token in httpOnly Secure
     SameSite=Strict cookie. Failure: 401, constant-time verify, same
     message for wrong-email vs wrong-password.
   - `POST /api/v1/auth/refresh` — rotate: issue new refresh token in the
     same family, revoke the old one. **If a revoked token is presented,
     revoke the entire family** and return 401.
   - `POST /api/v1/auth/logout` — revoke current family, clear cookie.
   - Mark login/refresh with `# public: credential exchange endpoints`.
4. Replace the placeholder in `api/deps.py`: `get_current_user` validates
   the JWT and loads the user; `get_current_admin` checks role==admin.
5. Seed script `scripts/create_admin.py` (reads email+password from env
   vars, for first admin only).
6. Tests in `tests/test_auth.py` mapping 1:1 to acceptance criteria,
   including the refresh-reuse → family-revocation case.

Out of scope: A1 (admin creates users), A3 (API keys), A4 (2FA), rate
limiting (E2). Do not implement these.

Follow every rule in AGENTS.md. This story touches auth — flag your
summary for human security review.
