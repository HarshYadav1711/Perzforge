# Task 11 — Story B4: Artifact storage, model registry, MLflow
# Attach: 00-PROJECT-CONTEXT.md · AGENTS.md · docs/PRD.md (Epic B) · docs/ARCHITECTURE.md (§3, §5)
# Pre-req: MVP merged (through F1)

Implement story B4: jobs produce versioned model artifacts in MinIO, and
every job's metrics land in MLflow.

Scope:
1. Infrastructure: uncomment/add `minio` in docker-compose; add `mlflow`
   service (image ghcr.io/mlflow/mlflow, backend-store-uri postgresql://…
   pointing at a dedicated `mlflow` database created via an init script,
   artifact root s3://mlflow/ with MINIO env credentials). Both bound to
   127.0.0.1/Tailscale only. Settings gain MINIO_ENDPOINT/KEY/SECRET and
   MLFLOW_TRACKING_URI.
2. Storage seam: `api/storage.py` — a thin S3 client (boto3, endpoint_url
   from settings) with put/get/presign/delete and per-user prefix
   convention `users/{user_id}/…`. All MinIO access goes through this
   module; nothing else imports boto3.
3. Worker → MLflow: inject MLFLOW_TRACKING_URI + MLFLOW_EXPERIMENT_NAME
   (=job name) into every job container's env. Jobs that use mlflow get
   tracking for free; jobs that don't are unaffected. Record the run id:
   after container exit, look up the run by experiment+start-time tag the
   worker sets via env (MLFLOW_RUN_TAG_JOB_ID={job_id}) and store
   mlflow_run_id on the Job row when found (best effort, never fail the job).
4. Artifact contract: containers write outputs to /workspace/outputs
   (the per-job volume from B3). On SUCCEEDED, worker uploads its contents
   to MinIO at models/{user_id}/{job_name}/{auto_version}/ and creates a
   `Model` row — id, user_id, name, version (int, auto-increment per
   user+name), source_job_id, minio_prefix, size_bytes, framework
   (nullable), created_at. Empty outputs dir → no model row, not an error.
5. Quota: storage_mb consumed via the E1 engine before upload; over-quota
   → job still SUCCEEDED but model marked absent + error surfaced in the
   job's final log line and API response field.
6. Routes: `GET /api/v1/models` (own, paginated), `GET /models/{id}`
   (ownership → 404), `GET /models/{id}/download` → presigned URLs
   (15-min expiry) for the artifact files, `DELETE /models/{id}` →
   removes MinIO prefix + row, releases quota.
7. Dashboard: Models page — list, sizes, source-job link, download.
   MLflow link-out in the job detail page when mlflow_run_id exists.
8. Tests: upload path with a MinIO test container (or moto if flaky in
   CI), version auto-increment, per-user prefix isolation (user A cannot
   presign user B's model → 404), quota-exceeded surfaces correctly,
   empty outputs no-op.

Out of scope: model deployment (C1), MLflow UI auth hardening (it stays
Tailscale-only), artifact dedup.

Commit message:
feat(B4): versioned model registry with MLflow-instrumented job runs

Job containers now inherit tracking credentials transparently, and
successful runs promote /workspace/outputs into per-user, auto-versioned
MinIO prefixes behind presigned access. Storage rides the existing quota
engine, and a single S3 seam keeps object-store coupling out of the
application layer.
