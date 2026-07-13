"""Live job log WebSocket endpoint (story B2)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.deps import Principal, UserRole, resolve_principal_from_token
from api.models import Job, JobLog, JobStatus
from api.queue import get_redis
from api.services.job_log_stream import LogWebSocketRelay

router = APIRouter(prefix="/jobs", tags=["jobs"])

WS_UNAUTHENTICATED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404

FINISHED_STATUSES = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}


async def _load_job(db: AsyncSession, job_id: uuid.UUID) -> Job | None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


def _job_visible_to_principal(job: Job, principal: Principal) -> bool:
    return job.user_id == principal.user.id or principal.user.role == UserRole.admin


def _require_jobs_read_scope(principal: Principal) -> None:
    if "jobs:read" not in principal.scopes:
        raise WebSocketException(code=WS_FORBIDDEN, reason="Insufficient scope")


@router.websocket("/{job_id}/logs")
async def stream_job_logs(
    websocket: WebSocket,
    job_id: uuid.UUID,
    token: str | None = Query(default=None, description="JWT or API key bearer token"),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    if not token:
        raise WebSocketException(code=WS_UNAUTHENTICATED, reason="Not authenticated")

    try:
        principal = await resolve_principal_from_token(token, db)
    except HTTPException:
        raise WebSocketException(code=WS_UNAUTHENTICATED, reason="Not authenticated") from None

    _require_jobs_read_scope(principal)

    job = await _load_job(db, job_id)
    if job is None or not _job_visible_to_principal(job, principal):
        raise WebSocketException(code=WS_NOT_FOUND, reason="Job not found")

    await websocket.accept()
    relay = LogWebSocketRelay(websocket)

    if job.status in FINISHED_STATUSES:
        result = await db.execute(select(JobLog).where(JobLog.job_id == job.id))
        for log_row in result.scalars().all():
            await relay.send_line(log_row.content)
        await websocket.close()
        return

    await relay.replay_buffer(redis, str(job.id))
    eof = await relay.relay_live(redis, str(job.id))
    if eof is not None:
        await relay.send_eof(eof)
    await websocket.close()
