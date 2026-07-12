"""Job submission and listing routes (story B1)."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.deps import Principal, UserRole, require_scopes
from api.models import Job, JobStatus
from api.queue import enqueue_job, get_redis
from api.schemas.job import JobSpec, SubmitJobRequest

router = APIRouter(prefix="/jobs", tags=["jobs"])

ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)


class JobResponse(BaseModel):
    id: uuid.UUID
    name: str
    spec: JobSpec
    status: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    worker_id: uuid.UUID | None
    exit_code: int | None
    error_message: str | None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    limit: int
    offset: int


def _to_job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        name=job.name,
        spec=JobSpec.model_validate(job.spec),
        status=job.status.value,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        worker_id=job.worker_id,
        exit_code=job.exit_code,
        error_message=job.error_message,
    )


async def _count_active_jobs(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Job)
        .where(Job.user_id == user_id, Job.status.in_(ACTIVE_JOB_STATUSES))
    )
    return result.scalar_one()


async def _get_owned_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    principal: Principal,
) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.user_id != principal.user.id and principal.user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return job


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def submit_job(
    body: SubmitJobRequest,
    principal: Principal = Depends(require_scopes("jobs:write")),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    active_jobs = await _count_active_jobs(db, principal.user.id)
    if active_jobs >= settings.max_concurrent_jobs_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Concurrent job limit reached "
                f"({settings.max_concurrent_jobs_per_user} active jobs per user)"
            ),
        )

    job = Job(
        user_id=principal.user.id,
        name=body.name,
        spec=body.spec.model_dump(),
        status=JobStatus.QUEUED,
        queued_at=datetime.now(UTC),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    try:
        await enqueue_job(redis, str(job.id))
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Queue enqueue failed: {exc}"
        job.finished_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(job)

    return _to_job_response(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_scopes("jobs:read")),
    db: AsyncSession = Depends(get_db),
):
    filters = [Job.user_id == principal.user.id]
    if status_filter is not None:
        filters.append(Job.status == status_filter)

    total_result = await db.execute(select(func.count()).select_from(Job).where(*filters))
    total = total_result.scalar_one()

    result = await db.execute(
        select(Job).where(*filters).order_by(Job.queued_at.desc()).limit(limit).offset(offset)
    )
    items = [_to_job_response(job) for job in result.scalars().all()]
    return JobListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    principal: Principal = Depends(require_scopes("jobs:read")),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_owned_job(db, job_id, principal)
    return _to_job_response(job)
