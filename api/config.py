"""Central settings. All secrets come from environment / .env — never hardcoded."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    environment: str = "dev"
    allowed_image_prefixes: str = "python:,pytorch/,tensorflow/,nvidia/cuda"
    max_concurrent_jobs_per_user: int = 2
    max_jobs_per_day_per_user: int = 10
    max_storage_mb_per_user: int = 2048
    max_instances_per_user: int = 1
    max_llm_tokens_per_day_per_user: int = 50000
    max_live_endpoints_per_user: int = 1
    quota_counter_ttl_seconds: int = 48 * 60 * 60
    job_queue_key: str = "perzforge:jobs:queue"
    worker_lock_key: str = "perzforge:worker:lock"
    worker_lock_ttl_seconds: int = 30
    worker_lock_heartbeat_seconds: int = 10
    worker_brpop_timeout_seconds: int = 5
    job_log_tail_lines: int = 10000
    job_log_replay_max_lines: int = 5000
    job_log_ws_send_timeout_seconds: float = 0.05
    job_log_ws_thin_interval: int = 10
    # Rate limit tiers (story E2)
    rate_limit_default_per_min: int = 60
    rate_limit_default_burst: int = 90
    rate_limit_auth_per_min: int = 5
    rate_limit_auth_burst: int = 5
    rate_limit_jobs_write_per_hour: int = 10
    rate_limit_jobs_write_burst: int = 10
    rate_limit_llm_per_min: int = 20
    rate_limit_llm_burst: int = 20
    # Object storage / experiment tracking (story B4)
    minio_endpoint: str = "http://127.0.0.1:9000"
    minio_access_key: str = "perzforge"
    minio_secret_key: str = "changeme-minio-pass"
    minio_bucket: str = "models"
    minio_region: str = "us-east-1"
    minio_secure: bool = False
    mlflow_tracking_uri: str = "http://127.0.0.1:5000"
    # Docker network for job containers (empty = network_mode none; set to reach MLflow)
    docker_job_network: str = ""
    # Model serving (story C1)
    serve_runner_image: str = "perzforge/serve-runner:latest"
    serving_network_name: str = "perzforge-serving"
    serving_artifact_root: str = "/var/lib/perzforge/endpoints"
    serving_health_timeout_seconds: int = 60
    serving_predict_timeout_seconds: float = 30.0
    serving_container_port: int = 8000
    serving_reconcile_on_startup: bool = True

    def image_prefixes(self) -> tuple[str, ...]:
        return tuple(prefix.strip() for prefix in self.allowed_image_prefixes.split(",") if prefix.strip())


settings = Settings()
