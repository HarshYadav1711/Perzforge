# PRD — Perzforge: Self-Hosted Mini-Cloud & ML Platform

**Author:** Harsh · **Status:** Draft v1 · **Last updated:** July 2026
**Companion doc:** `ml-platform-architecture.md` (the *how*; this doc is the *what/why*)

---

## 1. Problem Statement

Cloud platforms (AWS/GCP/Azure) make compute, storage, and ML infrastructure accessible — but they're expensive for students, and using them teaches you to *consume* infrastructure, not to *build* it. Meanwhile, capable hardware (a gaming laptop with a CUDA GPU) sits idle most of the day.

**Perzforge turns personal hardware into a small, multi-user cloud:** remotely accessible Linux instances, S3-compatible storage, GPU-scheduled ML jobs, and self-hosted LLM serving — free, private, and built from scratch as a portfolio-grade systems project.

## 2. Goals & Non-Goals

### Goals
1. Owner can control all services from anywhere (phone, college laptop) with zero exposed ports.
2. Users can submit ML jobs that run on the GPU, with live logs and stored artifacts.
3. Users can launch small Linux instances and SSH into them.
4. Users can call a self-hosted LLM through an OpenAI-compatible API with their own key.
5. The system is safe to share with friends: quotas, rate limits, and isolation are enforced by the platform, not by trust.
6. Every major component maps to a real-world equivalent (EC2/S3/SageMaker) so skills and vocabulary transfer directly to industry.

### Non-Goals (explicitly out of scope for v1)
- Public sign-ups / anonymous users (invite-only, admin creates accounts)
- Billing or payments of any kind
- High availability / uptime guarantees (GPU node is a laptop; that's accepted)
- Training large models (>3B params) — hardware can't; platform doesn't pretend to
- Kubernetes, multi-region, autoscaling (future work, not v1)
- Mobile app (responsive web dashboard is enough)

## 3. Users & Personas

| Persona | Description | Primary needs |
|---|---|---|
| **Admin (Harsh)** | Builds and operates the platform; also its heaviest user | Full control, monitoring, user management, runs own ML experiments (incl. exoplanet detection) |
| **Friend-Developer** | CS classmate with a project | Launch an instance to host a demo; call the LLM API from their code |
| **Friend-ML-Student** | Classmate learning ML | Submit a training job without owning a GPU; compare runs; download trained model |

## 4. User Stories & Acceptance Criteria

Written to be directly usable as tasks in Cursor/Codex. Each story = one buildable unit with testable "done" conditions.

### Epic A — Access & Accounts
- **A1.** As an admin, I can create a user account with an email and temporary password.
  ✅ `POST /admin/users` (admin-only) creates user; new user forced to change password on first login.
- **A2.** As a user, I can log in and stay logged in securely.
  ✅ JWT access (15 min) + rotating refresh token in httpOnly cookie; refresh reuse revokes the token family.
- **A3.** As a user, I can create/revoke named API keys with scopes.
  ✅ Key shown once; stored hashed; revoked key fails within 1 request; scopes enforced.
- **A4.** As an admin, I can enable TOTP 2FA on my account.
  ✅ QR enrollment, code required at login, hashed recovery codes.

### Epic B — ML Jobs
- **B1.** As a user, I can submit a training job (image + command + optional dataset ref) via API or dashboard.
  ✅ `POST /jobs` validates spec (Pydantic, unknown fields rejected), checks quota, returns job ID, status `QUEUED`.
- **B2.** As a user, I can watch my job's logs live.
  ✅ WebSocket `GET /jobs/{id}/logs` streams within 2s of container output; reconnect resumes from last line.
- **B3.** As a user, my job runs on the GPU in an isolated container.
  ✅ Container: non-root, cap-drop ALL, memory/CPU limits, `--gpus all` only if requested; owner-only visibility (foreign job ID → 404).
- **B4.** As a user, my job's metrics appear in MLflow and artifacts land in the model registry.
  ✅ MLflow run linked from job page; artifacts in MinIO under `models/{user}/{name}/{version}`.
- **B5.** As a user, I can cancel my queued/running job.
  ✅ `POST /jobs/{id}/cancel` stops container ≤10s, status `CANCELLED`.
- **B6.** As the platform, I wake the GPU node when jobs are waiting.
  ✅ Job queued + worker offline → WoL packet sent; job starts without human action when node boots.

### Epic C — Model Serving
- **C1.** As a user, I can deploy a registered model as an inference endpoint with one click.
  ✅ `POST /models/{id}/deploy` → endpoint `LIVE` with a route; predictable JSON in/out.
- **C2.** As a user, I can call the shared LLM with my API key using the OpenAI SDK.
  ✅ `POST /llm/v1/chat/completions` works with unmodified `openai` client (base_url swap); streaming supported.
- **C3.** As the platform, I meter and limit LLM usage per user.
  ✅ Tokens logged per request; daily budget exceeded → 429 with clear message; usage visible to user on dashboard.

### Epic D — Compute Instances
- **D1.** As a user, I can launch a Linux instance from a size preset with my SSH public key.
  ✅ `POST /instances` → SSH reachable ≤60s; key injected; micro/small/medium presets enforce CPU/RAM/disk limits.
- **D2.** As a user, I can start/stop/destroy my instances from the dashboard.
  ✅ State changes reflect ≤10s; destroy releases quota.
- **D3.** As the platform, I keep instances contained.
  ✅ Unprivileged; no host mounts; outbound port 25 blocked; per-instance disk quota; idle auto-stop after 7 days (configurable).

### Epic E — Quotas, Limits, Safety
- **E1.** As the platform, I enforce per-user quotas on everything expensive.
  ✅ Concurrent jobs, instance count/RAM/disk, storage GB, LLM tokens/day — exceeding any returns a 4xx naming the limit.
- **E2.** As the platform, I rate-limit every route.
  ✅ Redis token bucket; 429 + Retry-After; auth routes 5/min/IP.
- **E3.** As an admin, I can see an append-only audit log.
  ✅ Auth events, key changes, job/instance lifecycle, quota edits — who/what/when/IP, filterable in dashboard.

### Epic F — Dashboard & Observability
- **F1.** As a user, I see my jobs, models, endpoints, instances, and usage in one web UI.
- **F2.** As an admin, I see node status, GPU utilization, queue depth, and alerts (Grafana embedded or linked).
  ✅ Alert fires on: auth-failure spike, worker offline >X min with queued jobs, GPU busy with empty queue.

### Epic G — Astro Workload (dogfooding)
- **G1.** As the admin, I train an exoplanet transit classifier (TESS light curves) end-to-end on the platform.
  ✅ Dataset in MinIO → job on scheduler → metrics in MLflow → model deployed as endpoint. Serves as the platform's acceptance test.

## 5. MVP Definition (what "v1 shipped" means)

**MVP = Epics A (1–3) + B (1–5) + E (1–2) + minimal F1.**
Instances (D), LLM serving (C), 2FA, WoL, audit log UI, and astro workloads are fast-follows in that order. If B2 (live logs) proves hard, MVP may ship with poll-based logs — streaming is a fast-follow, not a blocker.

## 6. Success Metrics

- **M1:** Owner submits and completes a GPU training job from outside the home network. (MVP gate)
- **M2:** ≥3 real users each successfully run a job or instance without admin hand-holding.
- **M3:** Zero security incidents attributable to missing auth/quota checks; every API route has an explicit auth dependency (CI-verified).
- **M4:** Platform survives 2 weeks of normal use without manual restarts of the control plane.
- **M5:** Exoplanet model trained and served entirely on-platform (G1).
- **M6 (career):** Project produces a live demo + README + architecture doc + this PRD in one public repo, referenced in resume/interviews.

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| GPU node is a daily-driver laptop | Jobs stall when it's in use/off | WoL + queue tolerates offline worker; honest UX ("worker offline, job queued"); mini PC later |
| 4GB VRAM | Training and LLM can't coexist | VRAM-aware scheduling: unload Ollama before training jobs |
| Friend misuse / compromised instance | Home IP abused, host at risk | Unprivileged containers, egress firewall, hard quotas, audit log |
| Solo dev scope creep | Never ships | MVP definition above is the contract; everything else is fast-follow |
| Home power/network outages | Downtime | Accepted (non-goal); BIOS auto-power-on; document as known limitation |

## 8. Working Notes for AI-Assisted Development (Cursor/Codex)

- Treat each user story (A1, B1…) as one agent task; paste the story + relevant architecture-doc section as context.
- Keep both docs in the repo root (`/docs`); reference them in `AGENTS.md` / Cursor rules so the agent always builds against the agreed design.
- Non-negotiable rules to put in the agent's instructions: every route has an auth dependency; ownership check on every object fetch; no `shell=True`; Pydantic `extra="forbid"`; secrets only via env.
- Require the agent to write tests per acceptance criterion before marking a story done.
- Review all auth/security code by hand — AI-generated security logic is exactly where subtle bugs hide.
