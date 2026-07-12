# Task 04 — Story B1: Job submission API
# Attach: AGENTS.md · docs/PRD.md (Epic B) · docs/ARCHITECTURE.md (§2 lifecycle, §3, §4)
# Pre-req: Epic A merged

Implement story B1: authenticated users submit ML jobs; jobs land in Postgres
and the Redis queue. (Execution is B3 — not this task.)

Scope:
1. Model + migration: `Job` — id (UUID), user_id FK, name, spec JSONB,
   status enum QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED, queued_at,
   started_at nullable, finished_at nullable, worker_id nullable,
   exit_code nullable, error_message nullable.
2. Spec schema (Pydantic, extra="forbid"): image (str), command (list[str] —
   NEVER a shell string), env (dict[str,str], default {}), gpu (bool,
   default false), timeout_minutes (int, default 60, max 720).
   Image allow-list check: must start with a prefix from settings
   ALLOWED_IMAGE_PREFIXES (default: "python:", "pytorch/", "tensorflow/",
   "nvidia/cuda"). Reject anything else with a clear 422.
3. `POST /api/v1/jobs` (require_scopes("jobs:write") or JWT): validate,
   check per-user concurrent-job count against a hard cap from settings
   (MAX_CONCURRENT_JOBS_PER_USER, default 2; full quota system is E1),
   insert row, LPUSH job id to Redis list "perzforge:jobs:queue" — insert
   and enqueue must not desync: enqueue after commit, and if enqueue fails
   mark the job FAILED with error_message.
4. `GET /api/v1/jobs` — caller's jobs, newest first, paginated, filter by
   status. `GET /api/v1/jobs/{id}` — ownership or admin; foreign → 404.
5. Tests: valid submit → row QUEUED + id in Redis (use fakeredis or a
   redis test container via pytest fixture); shell-string command rejected;
   unknown spec field rejected; disallowed image rejected; over-cap → 429
   naming the limit; foreign job → 404.

Out of scope: execution, logs, cancellation, WoL, artifacts.

Commit message:
feat(B1): validated job submission with transactional queue handoff

Job specs are strict-schema JSONB with an image allow-list and list-only
command arrays, closing the shell-injection class at the API boundary.
Enqueue follows commit with failure reconciliation so Postgres and Redis
cannot silently diverge. Per-user concurrency caps ship as a stopgap
until the E1 quota engine lands.
