"""Centralized quota enforcement (story E1)."""
import enum
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models import Job, JobStatus, Quota, User

ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING)
QUOTA_COUNTER_TTL_SECONDS = settings.quota_counter_ttl_seconds


class QuotaResource(str, enum.Enum):
    CONCURRENT_JOBS = "concurrent_jobs"
    JOBS_PER_DAY = "jobs_per_day"
    STORAGE_MB = "storage_mb"
    INSTANCES = "instances"
    LLM_TOKENS_PER_DAY = "llm_tokens_per_day"


QUOTA_LIMIT_NAMES: dict[QuotaResource, str] = {
    QuotaResource.CONCURRENT_JOBS: "max_concurrent_jobs",
    QuotaResource.JOBS_PER_DAY: "max_jobs_per_day",
    QuotaResource.STORAGE_MB: "max_storage_mb",
    QuotaResource.INSTANCES: "max_instances",
    QuotaResource.LLM_TOKENS_PER_DAY: "max_llm_tokens_per_day",
}

DAILY_REDIS_RESOURCES = frozenset(
    {
        QuotaResource.JOBS_PER_DAY,
        QuotaResource.LLM_TOKENS_PER_DAY,
    }
)

ABSOLUTE_REDIS_RESOURCES = frozenset(
    {
        QuotaResource.STORAGE_MB,
        QuotaResource.INSTANCES,
    }
)


class QuotaExceededError(Exception):
    def __init__(self, detail: str, quota: str, limit: int, current: int) -> None:
        self.detail = detail
        self.quota = quota
        self.limit = limit
        self.current = current
        super().__init__(detail)

def _day_key(now: datetime | None = None) -> str:
    stamp = now or datetime.now(UTC)
    return stamp.strftime("%Y%m%d")


def quota_counter_key(
    user_id: uuid.UUID,
    resource: QuotaResource,
    *,
    day: str | None = None,
) -> str:
    if resource in DAILY_REDIS_RESOURCES:
        return f"perzforge:quota:{user_id}:{resource.value}:{day or _day_key()}"
    return f"perzforge:quota:{user_id}:{resource.value}"


def default_quota_values() -> dict[str, int]:
    return {
        "max_concurrent_jobs": settings.max_concurrent_jobs_per_user,
        "max_jobs_per_day": settings.max_jobs_per_day_per_user,
        "max_storage_mb": settings.max_storage_mb_per_user,
        "max_instances": settings.max_instances_per_user,
        "max_llm_tokens_per_day": settings.max_llm_tokens_per_day_per_user,
    }


async def get_or_create_quota(db: AsyncSession, user: User) -> Quota:
    result = await db.execute(select(Quota).where(Quota.user_id == user.id))
    quota = result.scalar_one_or_none()
    if quota is not None:
        return quota

    values = default_quota_values()
    quota = Quota(user_id=user.id, **values)
    db.add(quota)
    await db.commit()
    await db.refresh(quota)
    return quota


def _limit_for(quota: Quota, resource: QuotaResource) -> int:
    return int(getattr(quota, QUOTA_LIMIT_NAMES[resource]))


async def _count_concurrent_jobs(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Job)
        .where(Job.user_id == user_id, Job.status.in_(ACTIVE_JOB_STATUSES))
    )
    return int(result.scalar_one())


async def _read_redis_counter(redis: Redis, key: str) -> int:
    raw = await redis.get(key)
    if raw is None:
        return 0
    return int(raw)


async def current_usage(
    db: AsyncSession,
    redis: Redis,
    user: User,
    resource: QuotaResource,
) -> int:
    if resource == QuotaResource.CONCURRENT_JOBS:
        return await _count_concurrent_jobs(db, user.id)
    return await _read_redis_counter(redis, quota_counter_key(user.id, resource))


async def enforce(
    db: AsyncSession,
    redis: Redis,
    user: User,
    resource: QuotaResource,
    amount: int = 1,
) -> None:
    """Check (and for Redis-backed resources, consume) quota. Raises QuotaExceededError."""
    if amount < 1:
        raise ValueError("amount must be >= 1")

    quota = await get_or_create_quota(db, user)
    limit = _limit_for(quota, resource)
    current = await current_usage(db, redis, user, resource)
    projected = current + amount

    if projected > limit:
        name = QUOTA_LIMIT_NAMES[resource]
        raise QuotaExceededError(
            detail=f"{name} quota exceeded ({current}/{limit})",
            quota=name,
            limit=limit,
            current=current,
        )

    if resource in DAILY_REDIS_RESOURCES or resource in ABSOLUTE_REDIS_RESOURCES:
        key = quota_counter_key(user.id, resource)
        new_value = await redis.incrby(key, amount)
        if new_value == amount or resource in DAILY_REDIS_RESOURCES:
            await redis.expire(key, QUOTA_COUNTER_TTL_SECONDS)


async def usage_snapshot(
    db: AsyncSession,
    redis: Redis,
    user: User,
) -> dict[str, dict[str, int]]:
    quota = await get_or_create_quota(db, user)
    snapshot: dict[str, dict[str, int]] = {}
    for resource in QuotaResource:
        name = QUOTA_LIMIT_NAMES[resource]
        snapshot[name] = {
            "limit": _limit_for(quota, resource),
            "current": await current_usage(db, redis, user, resource),
        }
    return snapshot
