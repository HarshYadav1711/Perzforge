"""Redis job queue helpers (story B1)."""
from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from api.config import settings

JOB_QUEUE_KEY = settings.job_queue_key

_redis: Redis | None = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    yield _redis


async def enqueue_job(redis: Redis, job_id: str) -> None:
    await redis.lpush(JOB_QUEUE_KEY, job_id)


def set_redis_client(client: Redis | None) -> None:
    global _redis
    _redis = client
