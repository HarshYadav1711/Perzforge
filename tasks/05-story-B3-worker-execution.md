# Task 05 — Story B3: Worker agent executes jobs
# Attach: AGENTS.md · docs/PRD.md (Epic B) · docs/ARCHITECTURE.md (§2, §5, §7.6)
# Pre-req: B1 merged

Implement story B3 in `worker/agent.py` (+ new worker/ modules as needed):
the GPU-node agent that turns QUEUED jobs into running containers.

Scope:
1. Worker loop: BRPOP "perzforge:jobs:queue" (timeout 5s) → load Job row →
   verify still QUEUED (skip if cancelled) → set RUNNING + started_at +
   worker_id (hostname) → execute → set terminal status + finished_at +
   exit_code.
2. Container execution via Docker SDK (docker.from_env()):
   - image from spec (already allow-listed at submit; re-verify anyway —
     defense in depth)
   - command as list, environment from spec.env
   - security hardening per ARCHITECTURE §7.6: user="1000:1000",
     cap_drop=["ALL"], security_opt=["no-new-privileges"],
     network_mode="none" for v1 (jobs get no network; documented limitation),
     mem_limit="6g", nano_cpus=4e9, pids_limit=256, read_only=True with a
     writable tmpfs at /tmp and a per-job volume at /workspace.
   - gpu jobs: device_requests=[docker.types.DeviceRequest(count=-1,
     capabilities=[["gpu"]])].
3. Timeout enforcement: container.wait with spec timeout; on expiry, stop
   (10s grace) → kill → status FAILED, error_message "timeout".
4. Log capture: stream container logs and (for now) persist the tail
   (last 10k lines) to a `job_logs` table (job_id, content, created_at) on
   completion. Live streaming is B2 — leave a clearly named seam
   (worker/logs.py, publish_line stub).
5. Crash safety: worker startup marks any job stuck in RUNNING with its own
   worker_id as FAILED "worker restarted" — no zombie jobs.
6. Singleton guard: a Redis lock (SET NX EX with heartbeat refresh) so two
   agents can't run on one node.
7. Tests: use a tiny real image (python:3.12-alpine echo) if Docker is
   available in the test env, else mock the SDK layer; cover success path,
   nonzero exit → FAILED, timeout path, and startup zombie-reaping.

Out of scope: live log streaming (B2), artifact upload (B4), WoL (B6),
cancellation signal handling beyond the pre-start check (B5 wires the rest).

Touches container execution — flag for human review.

Commit message:
feat(B3): hardened container execution engine for the GPU worker

Jobs now run in maximally constrained containers: cap-drop ALL, no-new-
privileges, read-only root, network-none, cgroup memory/CPU/pid ceilings,
and opt-in GPU via device requests. The agent survives its own crashes by
reaping orphaned RUNNING jobs at startup and holds a heartbeat lock to
guarantee single-writer semantics per node.
