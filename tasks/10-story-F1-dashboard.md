# Task 10 — Story F1: Minimal dashboard (MVP closer)
# Attach: AGENTS.md · docs/PRD.md (Epic F, §5 MVP) · docs/ARCHITECTURE.md (§5)
# Pre-req: MVP API complete (A1-A3, B1-B5, E1-E2)

Implement story F1: a web UI for the MVP surface. New top-level `web/`
directory, Next.js 15 App Router + TypeScript + Tailwind (all free/OSS;
no paid component libraries, no telemetry-heavy deps).

Scope:
1. Auth: login page → calls /auth/login; JWT kept in memory, refresh via
   the httpOnly cookie flow already shipped in A2; forced password-change
   screen honoring the A1 403 contract.
2. Pages: Jobs list (status chips, auto-refresh via polling every 5s —
   SSE/WS upgrade later), Job detail with LIVE LOGS over the B2 WebSocket
   (auto-scroll, pause, reconnect indicator), New Job form (image dropdown
   from allow-list, command as array editor, gpu toggle), API Keys page
   (create modal that shows the single-reveal key with copy button +
   "you won't see this again"), My Quota page (usage bars from /me/quota).
3. One consistent layout: sidebar nav, dark theme default, zero clutter.
   This is a systems tool — clarity over decoration.
4. API access through a single typed client module (web/lib/api.ts);
   base URL from env; WebSocket auth per the B2 contract.
5. Dev ergonomics: `npm run dev` proxies to the FastAPI port; README
   section added; docker-compose gains an optional `web` service for
   later single-command bring-up.
6. Tests: component tests for the key-reveal flow and job form validation
   (Vitest + Testing Library); a Playwright smoke: login → submit job →
   see it appear. Keep e2e minimal and non-flaky.

Out of scope: admin panel, model registry UI (Phase 2), instances UI,
charts/Grafana embeds, mobile polish.

Commit message:
feat(F1): operator dashboard closing the MVP loop end to end

Next.js App Router UI wired to the full MVP surface: session auth with
forced-rotation handling, live WebSocket log tailing with replay-aware
reconnects, single-reveal key issuance UX, and quota visibility. One typed
API client owns every network call, keeping the contract in a single seam
for the Phase 2 surface to extend.
