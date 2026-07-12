# Perzforge — Agent Instructions (Cursor / Codex / any AI assistant)

You are building **Perzforge**, a self-hosted mini-cloud & ML platform.
The design is already decided. Do not improvise architecture.

## Required reading (in this order) before any task
1. `docs/PRD.md` — what we're building, user stories with acceptance criteria
2. `docs/ARCHITECTURE.md` — components, data model, API design, security architecture

## Non-negotiable rules (violations = rejected PR)
1. **Every API route has an explicit auth dependency.** No exceptions, including "temporary" or "internal" routes. Public routes (login, health) must be explicitly marked with a `# public: <reason>` comment.
2. **Ownership check on every object fetch.** `GET /jobs/{id}` must verify the job belongs to the caller (or caller is admin). Return **404** (not 403) for objects the caller doesn't own.
3. **Never use `shell=True`**, string-interpolated shell commands, or f-strings inside SQL. Docker SDK with list args; SQLAlchemy parameterized queries only.
4. **All request bodies are Pydantic models with `model_config = ConfigDict(extra="forbid")`.**
5. **Secrets only via environment variables** (`api/config.py` Settings class). Never hardcode, never commit `.env`.
6. **Every user story ships with tests** that map 1:1 to its acceptance criteria (pytest, in `tests/`). A story is not done until its tests pass.
7. **Passwords: Argon2id** (`argon2-cffi`). **API keys: store SHA-256 hash only**, show plaintext once.
8. Rate limiting middleware wraps all routes (Redis token bucket) — implemented in story E2; until then leave the middleware stub in place, do not remove it.
9. Async SQLAlchemy + asyncpg. No sync DB calls inside request handlers.
10. Keep diffs scoped to the story being implemented. Do not refactor unrelated code in the same change.

## Conventions
- Python 3.12, FastAPI, SQLAlchemy 2.x async, Pydantic v2.
- Formatting: ruff (line length 100). Type hints everywhere.
- API base path: `/api/v1`. Errors: JSON `{"detail": "..."}`, never stack traces.
- DB migrations: Alembic, one migration per story that touches the schema.
- Commit style: `feat(A2): implement login with refresh rotation` — story ID in every commit.

## Workflow per story
1. Read the story + acceptance criteria in `docs/PRD.md`.
2. Read the relevant section of `docs/ARCHITECTURE.md` (data model / API design / security).
3. Write the tests for the acceptance criteria first.
4. Implement until tests pass.
5. Summarize what was built and list any deviations from the docs (deviations require human sign-off).

## Security code is human-reviewed
Anything touching auth, tokens, keys, quotas, or container execution gets flagged for
manual review by Harsh. Say so explicitly at the end of your summary when you touch these.
