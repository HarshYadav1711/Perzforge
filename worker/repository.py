"""Database helpers for the worker agent (story B3)."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

import api.database as database
from api.models import Job, JobLog, JobStatus


async def load_job(job_id: uuid.UUID) -> Job | None:
    async with database.SessionLocal() as session:
        return await session.get(Job, job_id)


async def reap_zombie_jobs(worker_hostname: str) -> int:
    async with database.SessionLocal() as session:
        cancelling_result = await session.execute(
            update(Job)
            .where(Job.worker_id == worker_hostname, Job.status == JobStatus.CANCELLING)
            .values(
                status=JobStatus.CANCELLED,
                finished_at=datetime.now(UTC),
                error_message=None,
            )
            .returning(Job.id)
        )
        running_result = await session.execute(
            update(Job)
            .where(Job.worker_id == worker_hostname, Job.status == JobStatus.RUNNING)
            .values(
                status=JobStatus.FAILED,
                error_message="worker restarted",
                finished_at=datetime.now(UTC),
            )
            .returning(Job.id)
        )
        await session.commit()
        return len(cancelling_result.fetchall()) + len(running_result.fetchall())


async def mark_job_running(job_id: uuid.UUID, worker_hostname: str) -> Job | None:
    async with database.SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            return None

        job.status = JobStatus.RUNNING
        job.worker_id = worker_hostname
        job.started_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(job)
        return job


async def finalize_job(
    job_id: uuid.UUID,
    *,
    status: JobStatus,
    exit_code: int | None,
    error_message: str | None,
    log_tail: str,
) -> None:
    async with database.SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return

        job.status = status
        job.exit_code = exit_code
        job.error_message = error_message
        job.finished_at = datetime.now(UTC)

        if log_tail:
            session.add(JobLog(job_id=job.id, content=log_tail))

        await session.commit()


async def get_job_status(job_id: uuid.UUID) -> JobStatus | None:
    async with database.SessionLocal() as session:
        result = await session.execute(select(Job.status).where(Job.id == job_id))
        return result.scalar_one_or_none()
