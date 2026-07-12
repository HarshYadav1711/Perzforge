"""Redis singleton lock for the worker agent (story B3)."""
import os
import uuid

from redis.asyncio import Redis

from api.config import settings


class WorkerLock:
    def __init__(self, redis: Redis, hostname: str) -> None:
        self._redis = redis
        self._hostname = hostname
        self._key = settings.worker_lock_key
        self._token = f"{hostname}:{os.getpid()}:{uuid.uuid4()}"

    async def acquire(self) -> bool:
        return bool(
            await self._redis.set(
                self._key,
                self._token,
                nx=True,
                ex=settings.worker_lock_ttl_seconds,
            )
        )

    async def refresh(self) -> bool:
        current = await self._redis.get(self._key)
        if current != self._token:
            return False
        await self._redis.expire(self._key, settings.worker_lock_ttl_seconds)
        return True

    async def release(self) -> None:
        current = await self._redis.get(self._key)
        if current == self._token:
            await self._redis.delete(self._key)
