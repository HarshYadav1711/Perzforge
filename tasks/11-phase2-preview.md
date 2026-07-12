# Task 11+ — Phase 2 preview (generate full prompts when MVP ships)

Sequence after F1, one story per task, same format:
- B4: MinIO artifact upload + model registry rows + MLflow tracking URI
  injection into job containers (uncomment MinIO in docker-compose; add
  mlflow service; boto3 client seam).
- C1: one-click model deploy → inference containers + routing table.
- C2: Ollama behind the OpenAI-compatible proxy (auth, streaming passthrough).
- C3: token metering into usage_log + daily budget via the E1 engine +
  E2 llm tier goes live.
- B6: Wake-on-LAN — control plane sends magic packet when queue non-empty
  and worker heartbeat stale.
- E3: append-only audit log + admin viewer.
- D1-D3: Incus instance provisioning (needs Track B / real Ubuntu host).
- G1: exoplanet pipeline as the platform's own acceptance test.

Do not start Phase 2 tasks from this stub — request the full prompt first.
