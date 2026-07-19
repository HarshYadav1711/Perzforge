# Task 16 — Story E3: Append-only audit log
# Attach: 00-PROJECT-CONTEXT.md · AGENTS.md · docs/PRD.md (Epic E) · docs/ARCHITECTURE.md (§7.7)
# Pre-req: none beyond MVP

Implement story E3: security-relevant events are recorded immutably and
reviewable.

Scope:
1. Model + migration: `AuditLog` — id (bigserial), actor_user_id nullable
   (system events), actor_api_key_id nullable, action (text, dotted
   taxonomy: auth.login.success, auth.login.failure, auth.refresh.reuse,
   key.create, key.revoke, job.submit, job.cancel, model.delete,
   endpoint.deploy, endpoint.stop, quota.update, user.create,
   user.disable, worker.wake), target (text, e.g. "job:uuid"), ip
   nullable, detail JSONB, created_at. NO update/delete routes exist;
   add a Postgres trigger raising an exception on UPDATE/DELETE of this
   table — append-only enforced in the database, not by convention.
2. Emission: `api/audit.py` — `async def emit(action, actor=None, key=None,
   target=None, ip=None, **detail)`. Fire-and-forget (task group /
   background task); audit failure logs an ERROR but never fails the
   request. Instrument the actions listed above at their call sites —
   grep-audit the codebase and list every instrumented site in the summary.
3. Sensitive-data rule: detail JSONB may never contain passwords, tokens,
   key material, or full request bodies. Enforce with a scrub function +
   a test that feeds poisoned detail and asserts redaction.
4. Routes: `GET /api/v1/admin/audit` — filter by action prefix, actor,
   target, time range; keyset pagination (created_at+id, not OFFSET —
   this table only grows).
5. Dashboard: admin-only Audit page — filterable table, relative times,
   detail expander.
6. Retention: documented decision only (keep forever for now; note
   partitioning as the future path when it hurts). No cron.
7. Tests: trigger blocks UPDATE/DELETE at the DB level; emission is
   non-blocking on induced failure; scrubber redacts; keyset pagination
   is stable across inserts; login failure + refresh-reuse events appear
   with correct actors.

Touches auth-adjacent surfaces — flag for human review.

Commit message:
feat(E3): database-enforced append-only audit trail

Security events now flow through a single scrubbed emitter into a table
that Postgres itself refuses to mutate — immutability is a trigger, not
a promise. Keyset-paginated admin review ships in the dashboard, and
instrumentation covers the full auth, key, job, and serving lifecycle.
