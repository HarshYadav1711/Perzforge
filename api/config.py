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

    def image_prefixes(self) -> tuple[str, ...]:
        return tuple(prefix.strip() for prefix in self.allowed_image_prefixes.split(",") if prefix.strip())


settings = Settings()
