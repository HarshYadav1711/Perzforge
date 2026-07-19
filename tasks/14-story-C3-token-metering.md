# Task 14 — Story C3: LLM usage metering & budgets
# Attach: 00-PROJECT-CONTEXT.md · AGENTS.md · docs/PRD.md (Epic C) · docs/ARCHITECTURE.md (§7.3)
# Pre-req: C2 merged

Implement story C3: every LLM call is metered; daily token budgets bind.

Scope:
1. Model + migration: `UsageLog` — id, api_key_id nullable, user_id,
   endpoint (text: "chat.completions"), tokens_in, tokens_out, latency_ms,
   status (ok/error/cutoff), created_at. Index (user_id, created_at).
2. Metering: non-streaming — read usage from Ollama's response (it
   returns prompt_eval_count/eval_count; map to tokens_in/out). Streaming —
   accumulate from the final chunk's usage fields; if absent, estimate
   via len(text)//4 and mark status accordingly (document the estimate).
   Write the row after response completion (background task, never blocks
   the reply).
3. Budget enforcement via E1 engine (max_llm_tokens_per_day): check
   BEFORE the call using tokens_in estimate + a floor for output; debit
   actual totals after. Over budget → 429 quota-shaped body naming the
   limit. Mid-stream budget exhaustion: allow the current response to
   finish (simplicity; note the decision), debit fully — next call blocks.
4. Surfacing: `GET /api/v1/me/usage?days=7` — daily aggregates
   (calls, tokens_in/out); dashboard usage page gains an LLM panel with
   a simple bar chart (recharts, already free) and remaining budget.
5. Admin: `GET /api/v1/admin/usage` — per-user aggregates, top consumers.
6. Tests: metering rows for both modes; estimate fallback path; budget
   check blocks pre-call; debit correctness; per-key attribution;
   aggregates endpoint math.

Out of scope: pricing/billing semantics, per-model budgets, alerting.

Touches quotas — flag for human review.

Commit message:
feat(C3): per-user token metering with pre-flight budget enforcement

Every completion now writes an attributed usage record — measured when
the backend reports it, conservatively estimated when it doesn't — and
daily budgets gate calls before tokens are spent. Users see their own
burn-down; admins see the platform's. The LLM surface is now safe to
hand to friends.
