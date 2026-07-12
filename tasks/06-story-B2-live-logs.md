# Task 06 — Story B2: Live log streaming
# Attach: AGENTS.md · docs/PRD.md (Epic B) · docs/ARCHITECTURE.md (§2, §4)
# Pre-req: B3 merged

Implement story B2: users watch job logs live over WebSocket.

Scope:
1. Worker side (fill the B3 seam): as container log lines arrive, PUBLISH
   each to Redis channel `perzforge:jobs:{id}:logs` AND RPUSH to a capped
   Redis list `perzforge:jobs:{id}:logbuf` (LTRIM to last 5000 lines) so
   late joiners get history. On job end, publish a sentinel
   `{"event":"eof","exit_code":N}` and persist the full tail to job_logs
   (existing B3 behavior).
2. API side: `WS /api/v1/jobs/{id}/logs` — authenticate BEFORE accept()
   (JWT or API key passed as query token or first message; document choice),
   ownership check (close with 4404 policy code if foreign), then: send
   logbuf history, SUBSCRIBE to the channel, relay lines until eof or client
   disconnect. Handle reconnect naturally: history replay covers the gap.
3. Backpressure: if the client can't keep up, drop to sending every Nth
   line with a "[stream thinned]" marker rather than buffering unbounded.
4. For finished jobs: skip pub/sub entirely, send persisted logs, close.
5. Tests: history + live relay (fakeredis pubsub or redis test container),
   auth-before-accept (unauthed close code), foreign job close code,
   finished-job replay path, eof sentinel closes cleanly.

Out of scope: dashboard UI (F1 consumes this), log search, multi-job merge.

Commit message:
feat(B2): resumable live log streaming over authenticated WebSockets

Log lines fan out through Redis pub/sub with a capped replay buffer, so
reconnecting clients recover history instead of gaps. Sockets authenticate
and authorize before the upgrade completes, finished jobs short-circuit to
persisted replay, and bounded thinning protects the worker from slow
consumers.
