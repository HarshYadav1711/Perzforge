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
    job_queue_key: str = "perzforge:jobs:queue"
    worker_lock_key: str = "perzforge:worker:lock"
    worker_lock_ttl_seconds: int = 30
    worker_lock_heartbeat_seconds: int = 10
    worker_brpop_timeout_seconds: int = 5
    job_log_tail_lines: int = 10000

    def image_prefixes(self) -> tuple[str, ...]:
        return tuple(prefix.strip() for prefix in self.allowed_image_prefixes.split(",") if prefix.strip())


settings = Settings()
