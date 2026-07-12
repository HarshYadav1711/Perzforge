# Task 07 — Story B5: Job cancellation
# Attach: AGENTS.md · docs/PRD.md (Epic B)
# Pre-req: B2 merged

Implement story B5: users cancel queued or running jobs.

Scope:
1. `POST /api/v1/jobs/{id}/cancel` — ownership or admin; foreign → 404.
   QUEUED: set CANCELLED directly (worker's B3 pre-start check already
   skips it). RUNNING: set status CANCELLING (add to enum + migration) and
   PUBLISH to `perzforge:jobs:{id}:control` the message {"cmd":"cancel"}.
   Terminal states → 409 "job already finished".
2. Worker: subscribe to the control channel of the job it is running;
   on cancel → container.stop(timeout=10) → kill if needed → status
   CANCELLED, finished_at set, eof sentinel published with
   {"event":"eof","cancelled":true}.
3. Safety net: if the worker misses the message (restart mid-cancel), the
   startup zombie-reaper (B3) plus a CANCELLING check in the reaper marks
   it CANCELLED, not FAILED.
4. Tests: cancel QUEUED; cancel RUNNING (mock/real container) reaches
   CANCELLED ≤ ~12s; double-cancel → 409; foreign → 404; reaper converts
   orphaned CANCELLING → CANCELLED.

Out of scope: bulk cancel, admin force-kill endpoint.

Commit message:
feat(B5): cooperative cancellation with crash-safe state convergence

Cancellation flows through a per-job control channel with a two-phase
CANCELLING→CANCELLED transition; graceful stop escalates to kill after a
grace window. The startup reaper now converges interrupted cancellations,
so no combination of worker crashes strands a job in a live state.
