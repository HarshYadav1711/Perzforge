# Project "Perzforge" — Self-Hosted ML Platform Architecture

*A mini AI Lab: GPU job scheduling, model registry, and LLM serving on your own hardware.*

---

## 1. Goals & Requirements

### Functional requirements
1. Users submit ML jobs (training or batch inference) via web dashboard or REST API.
2. Jobs are queued and scheduled onto a GPU worker (your TUF F15's 1650 Ti).
3. Jobs run in isolated Docker containers with GPU access; logs stream live to the dashboard.
4. Trained models are versioned and stored in a model registry (MinIO).
5. Any registered model can be deployed as an inference API endpoint with one click.
6. A small self-hosted LLM is served behind an OpenAI-compatible API with per-user API keys and rate limits.
7. Experiment metrics (loss curves, accuracy, params) are tracked and comparable across runs (MLflow).
8. Multi-user: you + a handful of friends, each with their own API key, job history, and quotas.

### Non-functional requirements
- **Scale:** 5–10 users, 1 GPU, a few jobs per day. Design for correctness, not throughput.
- **Availability:** Control plane should be always-on eventually; GPU node can be intermittent (it's your laptop).
- **Latency:** Job pickup within seconds of GPU node being online. LLM inference "good enough" (a 3B quantized model on a 1650 Ti gives roughly 15–30 tokens/sec).
- **Cost:** ~₹0 beyond electricity and an optional ₹100–800/yr domain.
- **Security:** Nothing exposed raw to the internet. Tailscale for private access, Cloudflare Tunnel only for deliberately public endpoints.

### Constraints
- One developer (you), part-time alongside college.
- Hardware today: TUF F15 (i5 12th gen, 16GB, GTX 1650 Ti 4GB) — dual duty as daily driver + GPU node.
- Later: cheap always-on mini PC as the control plane.
- Stack should use skills you're already selling on your resume: Python, FastAPI, Docker, ML tooling.

---

## 2. High-Level Architecture

```
                        Internet
                           │
              ┌────────────┴─────────────┐
              │ Cloudflare Tunnel        │  (public: dashboard*, model endpoints)
              └────────────┬─────────────┘
                           │
   Tailscale mesh (private network, all machines + your phone/college laptop)
   ────────────┬──────────────────────────────┬────────────────────
               │                              │
   ┌───────────▼───────────────┐   ┌──────────▼──────────────────┐
   │  CONTROL PLANE            │   │  GPU WORKER NODE            │
   │  (mini PC later; TUF now) │   │  (TUF F15, GTX 1650 Ti)     │
   │                           │   │                             │
   │  • API Gateway (FastAPI)  │   │  • Worker Agent (Python)    │
   │  • Dashboard (Next.js/    │   │    - polls queue            │
   │    React)                 │   │    - runs job containers    │
   │  • Redis (job queue +     │   │      via Docker SDK         │
   │    pub/sub for logs)      │   │    - streams logs to Redis  │
   │  • PostgreSQL (users,     │   │  • Docker + NVIDIA          │
   │    jobs, models metadata) │   │    Container Toolkit        │
   │  • MinIO (datasets,       │   │  • Ollama / llama.cpp       │
   │    model artifacts)       │   │    (LLM serving)            │
   │  • MLflow (experiment     │   │                             │
   │    tracking)              │   │  Woken via Wake-on-LAN      │
   │  • Grafana + Prometheus   │   │  when jobs are pending      │
   └───────────────────────────┘   └─────────────────────────────┘

   * dashboard public exposure is optional; default is Tailscale-only
```

### Job lifecycle (the core data flow)
1. User hits `POST /jobs` with a job spec (Docker image or Git repo, command, resource needs, dataset ref).
2. API Gateway validates auth/quota → writes job row (`status=QUEUED`) in Postgres → pushes job ID onto Redis queue.
3. If no GPU worker is online, control plane sends a Wake-on-LAN packet to the TUF.
4. Worker Agent pulls the job, marks `RUNNING`, pulls the dataset from MinIO, launches a Docker container with `--gpus all`.
5. Container stdout/stderr is streamed to Redis pub/sub → dashboard shows live logs via WebSocket. Metrics go to MLflow.
6. On completion, artifacts (model weights) are uploaded to MinIO, job marked `SUCCEEDED`/`FAILED`, GPU freed, next job pulled.
7. User optionally clicks "Deploy" → control plane instructs worker to run an inference container serving that model → endpoint registered and routed.

---

## 3. Data Model (PostgreSQL)

- **users** — id, email, password_hash, role (admin/user), created_at
- **api_keys** — id, user_id, key_hash, name, rate_limit_per_min, revoked
- **jobs** — id, user_id, name, spec_json (image, command, env, gpu: bool), status (QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED), queued_at, started_at, finished_at, worker_id, exit_code, mlflow_run_id
- **models** — id, user_id, name, version, source_job_id, minio_path, framework, size_bytes, created_at
- **endpoints** — id, model_id, name, status (STARTING/LIVE/STOPPED), container_id, route, created_at
- **workers** — id, hostname, tailscale_ip, mac_address (for WoL), gpu_name, vram_mb, status (ONLINE/OFFLINE/BUSY), last_heartbeat
- **usage_log** — api_key_id, endpoint_id, tokens_in/out or request count, timestamp (for rate limiting + per-user stats)

Keep job specs as JSONB — schemas evolve fast and you're the only maintainer.

---

## 4. API Design (FastAPI, `/api/v1`)

**Auth:** JWT for dashboard sessions; `Authorization: Bearer <api-key>` for programmatic access.

- `POST /auth/register`, `POST /auth/login`
- `POST /keys` / `GET /keys` / `DELETE /keys/{id}`
- `POST /jobs` — submit job → returns job ID
- `GET /jobs`, `GET /jobs/{id}` — list / status
- `GET /jobs/{id}/logs` — WebSocket, live log stream
- `POST /jobs/{id}/cancel`
- `GET /models`, `GET /models/{id}`
- `POST /models/{id}/deploy` → creates endpoint
- `GET /endpoints`, `POST /endpoints/{id}/stop`
- `POST /llm/v1/chat/completions` — OpenAI-compatible LLM proxy (auth + rate limit + usage logging, forwards to Ollama on the GPU node)
- `GET /workers` — node status, VRAM, current job (admin)
- `GET /admin/usage` — per-user stats

The OpenAI-compatible route is a big deal: any tool that works with the OpenAI SDK (LangChain apps, VS Code extensions, your friends' projects) works with **your** platform by changing one base URL.

---

## 5. Component Choices & Trade-offs

| Component | Choice | Why / trade-off |
|---|---|---|
| API + worker language | Python (FastAPI) | Your strongest language; async + WebSockets built in. Go would be faster but slower for you to ship. |
| Queue | Redis (lists + pub/sub) | Dead simple, doubles as log streaming bus. Celery/RabbitMQ is overkill for 1 worker; upgrade path exists. |
| Metadata DB | PostgreSQL | Boring and correct. SQLite would work but Postgres = zero migration pain later + resume keyword. |
| Job isolation | Docker + NVIDIA Container Toolkit | Industry standard; exactly how real platforms run jobs. K8s later, not now. |
| Object storage | MinIO | S3-compatible → your code uses `boto3`, so it ports to real AWS unchanged. |
| Experiment tracking | MLflow | De-facto standard, one Docker container, huge resume recognition. |
| LLM serving | Ollama (llama.cpp backend) | Trivial setup, runs Llama 3.2 3B / Phi-3-mini Q4 in 4GB VRAM. vLLM is the "serious" choice but needs more VRAM. |
| Dashboard | Next.js + Tailwind | Matches your full-stack experience; SSR not really needed but fine. |
| Private networking | Tailscale | Solves CGNAT, free for 3 users/100 devices, WireGuard underneath. |
| Public exposure | Cloudflare Tunnel | Free, no open ports, DDoS protection, real TLS certs. |
| Monitoring | Prometheus + Grafana + nvidia-smi exporter | GPU utilization graphs on your dashboard look fantastic in demos. |

**Explicit trade-offs made:**
- *Single queue, single GPU, no bin-packing scheduler.* Correct for now; the scheduler interface is where you extend later.
- *Worker polls the queue* rather than the control plane pushing. Simpler, survives network blips, natural fit for a node that sleeps.
- *No Kubernetes yet.* K8s on one node adds complexity without teaching you much you can't learn later; Docker SDK knowledge transfers.

---

## 6. GPU Node Specifics (TUF F15)

- Dual-boot Ubuntu 22.04/24.04 (recommended over WSL2 — cleaner NVIDIA + Docker behavior, and it *is* a server when booted into it). Windows stays for daily use.
- Install: NVIDIA driver, Docker, NVIDIA Container Toolkit, Tailscale, the Worker Agent (a systemd service).
- **Wake-on-LAN:** enable in BIOS + `ethtool -s eno1 wol g`. Works over Ethernet only — plug the TUF into the router when it's in "server duty." Control plane sends the magic packet when jobs queue up while the worker is offline.
- **Battery care:** cap charge at 60–80% in MyASUS/BIOS before leaving it plugged in 24/7.
- **VRAM budgeting:** 4GB is tight. Worker Agent should refuse to start a training job while the LLM is loaded (or auto-unload Ollama first). Make "VRAM-aware scheduling" a feature — it's a great interview story.
- Realistic training scope: fine-tuning small models (LoRA on 1–3B LLMs, CNNs, classical ML, small transformers). Not full LLM training — and that's fine; the *platform* is the project.

---

## 6.5 Compute Service — EC2-like Instances

The third pillar: on-demand Linux "instances" users can SSH into, provisioned through the same platform.

**Technology: Incus (LXD fork) system containers.** Unlike Docker app containers, these run full distros with systemd — apt, cron, multiple services, SSH daemon — indistinguishable from a small VPS to the user, but light enough that the TUF can host 5–10 alongside ML jobs. Installs on your existing Ubuntu; no hypervisor reinstall needed. When the mini PC arrives, Proxmox there gives you real KVM VMs via the same provisioning API pattern.

**Provisioning flow (the EC2 launch experience):**
1. `POST /instances` with `{name, size, image, ssh_public_key}` — sizes are presets: `micro` (1 vCPU/512MB), `small` (1/1GB), `medium` (2/2GB).
2. Control plane checks the user's quota, then calls the Incus REST API on the host: create container from image (Ubuntu 24.04/Debian 12), apply CPU/RAM/disk limits, inject SSH key via cloud-init.
3. Networking: either join the container to Tailscale (cleanest — user gets a stable private IP reachable anywhere) or NAT a unique SSH port on the host.
4. Return connection details: `ssh ubuntu@100.x.y.z`. Instance appears in the dashboard with start/stop/destroy buttons and live CPU/RAM graphs.

**Data model additions:**
- **instances** — id, user_id, name, size, image, status (PROVISIONING/RUNNING/STOPPED/DESTROYED), incus_name, tailscale_ip or ssh_port, created_at
- **quotas** — user_id, max_instances, max_total_ram_mb, max_disk_gb

**API additions:** `POST /instances`, `GET /instances`, `POST /instances/{id}/start|stop`, `DELETE /instances/{id}`, `GET /instances/{id}/metrics`.

**Safeguards (multi-tenant compute is the riskiest surface):**
- Hard CPU/RAM/disk limits on every container; disk via btrfs/ZFS storage pool with per-instance quotas.
- Unprivileged containers only; no host mounts.
- Egress firewall rules per container if you give friends access (prevent your home IP being used for abuse — you are the ISP now).
- Idle auto-stop after N days; quotas enforced at the API, not on trust.

**Resource budget note:** ML jobs and instances share the TUF's 16GB. Reserve headroom (e.g., instances capped at 6GB total) or make the scheduler instance-aware. On the mini PC later, instances move there and the TUF becomes pure GPU node — the clean end-state.

## 6.6 Astrophysics Workloads — the Space Angle

The platform doubles as an astrophysics data station. All of these run as ordinary jobs/services on the existing architecture — no redesign needed.

**A. Exoplanet detection (flagship ML project)**
- Data: NASA Kepler/TESS light curves — free via the MAST archive and the `lightkurve` Python library.
- Task: 1D CNN / transformer classifier that detects transit dips (planet crossing its star). Fits comfortably in 4GB VRAM.
- Platform fit: dataset in MinIO → training job on the GPU scheduler → metrics in MLflow → best model deployed as a "classify this light curve" API endpoint.
- Reference: Google/NASA's AstroNet work proves the approach; citizen-science versions have found real planets.

**B. Galaxy & asteroid classification**
- Galaxy Zoo images (morphology classification) and NASA NEO datasets — standard computer-vision jobs, good for exercising the platform with varied workloads.

**C. SatNOGS ground station (real hardware, ~₹2–3k)**
- RTL-SDR USB dongle + V-dipole antenna → receive NOAA weather satellite imagery, ISS packets, cubesat telemetry.
- Join the SatNOGS network: your station gets auto-scheduled to track satellites; observations feed real operators including university cubesat teams. Runs as a Docker service on the control plane; pass schedule + decoded images on your dashboard.
- This is actual participation in space operations, not simulation.

**D. Einstein@Home on idle GPU**
- BOINC container at lowest priority: when the job queue is empty, the GPU searches real telescope data for pulsars and gravitational waves. Scheduler preempts it the moment a user job arrives. "Idle cycles scan the universe" — great demo line, great scheduler-design story.

**Career note:** Indian space-sector startups (Pixxel, Digantara, Skyroot) and ISRO-adjacent teams hire exactly this profile — ML pipelines over satellite imagery/telemetry. This section turns the platform from "impressive infra project" into a domain-specific portfolio.

### Build order for this section
1. Exoplanet CNN first — pure software, uses the platform you're already building (slot into Phase 2–3 as your first *real* workload).
2. Einstein@Home container — one afternoon, once the scheduler has priorities.
3. SatNOGS station — when you have the mini PC (needs an always-on host + a window/roof spot for the antenna).

## 7. Security Architecture

Security is enforced in layers; a request must pass every layer. Nothing relies on trust.

### 7.1 Authentication
- **Dashboard sessions:** short-lived JWT access tokens (15 min) + rotating refresh tokens (7 days) stored in httpOnly, Secure, SameSite=Strict cookies. Refresh token rotation with reuse detection: if a refresh token is replayed, revoke the whole family (stolen-token defense).
- **Passwords:** Argon2id hashing (`argon2-cffi`), min length 12, checked against a breached-password list at registration. No composition rules theater.
- **2FA:** TOTP (pyotp + QR enrollment), mandatory for admin accounts, optional for users. Recovery codes generated once, stored hashed.
- **API keys (programmatic access):** format `pzf_<32 random bytes url-safe>`; only a SHA-256 hash is stored; plaintext shown exactly once at creation. Keys carry scopes (`jobs:write`, `llm:invoke`, `instances:manage`), optional expiry, per-key rate limit tier, and last-used tracking. Instant revocation.
- **Login protection:** per-account and per-IP attempt counters in Redis with exponential backoff lockout; all auth events audit-logged.

### 7.2 Authorization (RBAC + ownership)
- Roles: `admin`, `user`, `readonly`. Enforced as a FastAPI dependency on every route — no route ships without an explicit auth dependency (add a CI check/test that asserts this).
- **Ownership checks on every object access:** `GET /jobs/{id}` verifies `job.user_id == caller.id` (or admin). This kills IDOR, the most common real-world API vuln. Use 404, not 403, for objects the caller doesn't own — don't leak existence.
- Scoped API keys can never exceed their owner's role.

### 7.3 Rate Limiting & Quotas (defense against abuse *and* your own bugs)
- **Implementation:** Redis token-bucket per key, checked in middleware before any handler runs. Return `429` with `Retry-After` + standard `X-RateLimit-*` headers.
- **Tiers (tune later):**
  - Auth endpoints: 5/min per IP (brute-force control)
  - General API: 60/min per key
  - `POST /jobs`: 10/hour per user (a GPU job is expensive)
  - LLM completions: 20/min per key **and** a daily token budget per user (tokens metered from usage_log)
  - Instance creation: 5/day per user
- **Hard resource quotas (enforced in the API, stored in `quotas` table):** max concurrent jobs, max instances, max total instance RAM/disk, MinIO storage cap per user (checked before artifact upload), LLM tokens/day. Quota exceeded → clear 4xx error naming the limit.
- **Global circuit breakers:** platform-wide caps (e.g., total queued jobs, total running containers) so no combination of users can exhaust the host.

### 7.4 Input Validation & API Hygiene
- Pydantic models with strict types on every request body; reject unknown fields (`extra="forbid"`).
- Job specs: whitelist allowed Docker registries/images or require images built by your platform; never pass user strings into shell commands (Docker SDK with arg lists only — no `shell=True` anywhere in the codebase).
- File uploads: size limits, content-type checks, randomized object names in MinIO.
- CORS locked to your dashboard origin. Security headers via middleware: HSTS, X-Content-Type-Options, X-Frame-Options DENY, restrictive CSP on the dashboard.
- Uniform error responses — no stack traces or internal paths to clients (FastAPI exception handlers).

### 7.5 Secrets & Data Protection
- All secrets in `.env` (gitignored) or Docker secrets; a `.env.example` documents required vars. Pre-commit hook with `gitleaks` so a secret can never land in Git.
- Postgres/MinIO/Redis credentials unique per service; Redis with `requirepass` even on localhost.
- TLS everywhere users touch: Cloudflare Tunnel terminates public TLS; Tailscale encrypts private traffic (WireGuard). Nothing plaintext crosses a network you don't control.
- Backups (Postgres dumps + MinIO sync) encrypted at rest (age/restic) before leaving the machine.

### 7.6 Container & Host Hardening
- Job/inference containers: non-root user, `--memory`/`--cpus`/`--pids-limit` set, `--cap-drop ALL`, no host network, read-only root FS + tmpfs scratch, `no-new-privileges`. Never mount the Docker socket into a user container (that's root on the host).
- Incus instances: unprivileged only, per-instance disk quotas (btrfs/ZFS pool), egress firewall rules (block SMTP port 25 outright — spam prevention), idle auto-stop.
- Host: SSH keys only + fail2ban; UFW default-deny inbound, allow only Tailscale interface; unattended-upgrades for security patches; Postgres/MinIO/Redis/Ollama bound to localhost/Tailscale IPs — never 0.0.0.0 on a public interface.
- Dependency hygiene: Dependabot/`pip-audit` in CI; pinned versions with a lockfile.

### 7.7 Audit Logging & Detection
- **audit_log table:** every auth event, key creation/revocation, job submit, instance create/destroy, quota change, admin action — who, what, when, source IP. Append-only.
- Structured JSON app logs; Grafana alerts on anomalies: auth failure spikes, 429 storms, a user hitting quota ceilings repeatedly, GPU pegged with no queued job (cryptomining smell), unexpected egress volume from instances.
- `GET /admin/audit` in the dashboard so you can actually review it.

### 7.8 Resume Framing (security edition)
This layer is itself interview material: *"Implemented defense-in-depth API security: Argon2id + TOTP 2FA, rotating refresh tokens with reuse detection, scoped API keys, Redis token-bucket rate limiting, per-user resource quotas, RBAC with ownership checks, container sandboxing (cap-drop, non-root, read-only FS), and append-only audit logging."* Every phrase is a security-interview question you'll be able to answer from experience — this doubles as cybersecurity portfolio material on top of your Prodigy Infotech internship.

---

## 8. Build Phases

### Phase 0 — Foundation (weekend)
Dual-boot Ubuntu on TUF, Docker + NVIDIA toolkit, Tailscale on TUF + phone + any second device. Verify: `docker run --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi` and SSH over Tailscale from mobile data.
**Milestone:** remote GPU access from anywhere.

### Phase 1 — Core job runner (2–3 weeks) ⭐ the heart
FastAPI app: auth, `POST /jobs`, Redis queue, Postgres. Worker Agent: poll → run container → capture logs → update status. Log streaming via Redis pub/sub + WebSocket. CLI or minimal HTML page to submit and watch a job.
**Milestone:** submit an MNIST training job from your phone, watch logs live, get the trained model back.

### Phase 2 — Registry, MLflow, dashboard (2–3 weeks)
MinIO up; jobs auto-upload artifacts; `models` table + versioning. MLflow integrated (worker injects tracking URI into job env). Next.js dashboard: job list, live logs, model registry, GPU stats.
**Milestone:** compare two training runs' loss curves in your own UI.

### Phase 3 — Serving layer (2 weeks)
"Deploy" button → inference container from a registered model → routed endpoint. Ollama + OpenAI-compatible proxy with API keys, rate limits, usage logging.
**Milestone:** a friend uses your LLM API from their own code with a key you issued.

### Phase 3.5 — Compute service (1–2 weeks)
Install Incus, hand-create one instance to learn the flow, then wire `POST /instances` → Incus API with cloud-init SSH key injection, quotas, and dashboard start/stop controls.
**Milestone:** a friend runs `ssh ubuntu@<ip>` into an instance they launched from your dashboard.

### Phase 4 — Multi-node & polish (ongoing)
Buy mini PC → move control plane to it (everything is Docker Compose, so migration is one afternoon). Wake-on-LAN integration. Prometheus + Grafana. Quotas, admin panel, docs, architecture diagram in the README, demo video.
**Milestone:** control plane always-on; TUF sleeps until work arrives.

---

## 9. Scaling / Upgrade Path (what to revisit as it grows)

- **2nd GPU node** → workers register themselves (the `workers` table already supports it); scheduler becomes "pick best available node" — now it's a *cluster*.
- **Real scheduler** → priorities, VRAM bin-packing, preemption. Swap Redis list for Redis streams or RabbitMQ.
- **Kubernetes** → replace Docker SDK calls with K8s Jobs API; your abstractions map 1:1.
- **College/cloud GPUs** → a worker agent on any Linux box with a GPU joins your platform via Tailscale. This is the "AI Lab" endgame: one control plane, heterogeneous GPU fleet.
- **Storage growth** → MinIO erasure coding across disks, or point `boto3` at real S3 — zero code change.

## 10. Resume Framing

> **Perzforge — Self-hosted ML platform** · Python, FastAPI, Docker, Redis, PostgreSQL, MinIO, MLflow, Next.js
> Built a distributed ML platform with GPU-aware job scheduling, live log streaming (WebSockets/Redis pub-sub), versioned model registry (S3-compatible), one-click model deployment, and OpenAI-compatible LLM serving with per-user auth and rate limiting; serves N users across a Tailscale mesh with Wake-on-LAN GPU node orchestration.

Every keyword in that line is defensible in a deep-dive interview because you built each piece.
