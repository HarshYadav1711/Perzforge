"""Quota routes: user view + admin override (story E1)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.deps import get_current_admin, get_current_user
from api.models import Quota, User
from api.queue import get_redis
from api.quotas import get_or_create_quota, usage_snapshot

me_router = APIRouter(prefix="/me", tags=["me"])
admin_quota_router = APIRouter(prefix="/admin/users", tags=["admin"])


class QuotaLimitsResponse(BaseModel):
    max_concurrent_jobs: int
    max_jobs_per_day: int
    max_storage_mb: int
    max_instances: int
    max_llm_tokens_per_day: int


class QuotaUsageEntry(BaseModel):
    limit: int
    current: int


class MeQuotaResponse(BaseModel):
    limits: QuotaLimitsResponse
    usage: dict[str, QuotaUsageEntry]


class PatchQuotaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrent_jobs: int | None = Field(default=None, ge=0)
    max_jobs_per_day: int | None = Field(default=None, ge=0)
    max_storage_mb: int | None = Field(default=None, ge=0)
    max_instances: int | None = Field(default=None, ge=0)
    max_llm_tokens_per_day: int | None = Field(default=None, ge=0)


def _limits_response(quota: Quota) -> QuotaLimitsResponse:
    return QuotaLimitsResponse(
        max_concurrent_jobs=quota.max_concurrent_jobs,
        max_jobs_per_day=quota.max_jobs_per_day,
        max_storage_mb=quota.max_storage_mb,
        max_instances=quota.max_instances,
        max_llm_tokens_per_day=quota.max_llm_tokens_per_day,
    )


@me_router.get("/quota", response_model=MeQuotaResponse)
async def get_my_quota(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    snapshot = await usage_snapshot(db, redis, user)
    quota = await get_or_create_quota(db, user)
    return MeQuotaResponse(
        limits=_limits_response(quota),
        usage={name: QuotaUsageEntry(**values) for name, values in snapshot.items()},
    )


@admin_quota_router.patch("/{user_id}/quota", response_model=QuotaLimitsResponse)
async def patch_user_quota(
    user_id: uuid.UUID,
    body: PatchQuotaRequest,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No quota fields provided",
        )

    quota = await get_or_create_quota(db, target)
    for field, value in updates.items():
        setattr(quota, field, value)
    await db.commit()
    await db.refresh(quota)
    return _limits_response(quota)
