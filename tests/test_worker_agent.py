"""Story B3 worker agent tests."""
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

import api.database as database
from api.models import Job, JobLog, JobStatus, User, UserRole
from api.schemas.job import JobSpec
from api.security import hash_password
from worker.agent import _worker_redis, process_job
from worker.container import ContainerRunResult
from worker.lock import WorkerLock
from worker.repository import reap_zombie_jobs


def _job_spec() -> dict:
    return {
        "image": "python:3.12-alpine",
        "command": ["python", "-c", "print('ok')"],
        "env": {},
        "gpu": False,
        "timeout_minutes": 60,
    }


async def _create_queued_job(name: str = "worker-test") -> Job:
    async with database.SessionLocal() as session:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("correct-password-12"),
            role=UserRole.user,
            must_change_password=False,
        )
        session.add(user)
        await session.flush()
        job = Job(
            user_id=user.id,
            name=name,
            spec=_job_spec(),
            status=JobStatus.QUEUED,
            queued_at=datetime.now(UTC),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


@pytest.mark.asyncio
async def test_reap_zombie_jobs_marks_running_jobs_failed(fake_redis):
    hostname = "test-worker"
    async with database.SessionLocal() as session:
        user = User(
            email="zombie@example.com",
            password_hash=hash_password("correct-password-12"),
            role=UserRole.user,
            must_change_password=False,
        )
        session.add(user)
        await session.flush()
        job = Job(
            user_id=user.id,
            name="zombie",
            spec=_job_spec(),
            status=JobStatus.RUNNING,
            worker_id=hostname,
            started_at=datetime.now(UTC),
            queued_at=datetime.now(UTC),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    await reap_zombie_jobs(hostname)

    async with database.SessionLocal() as session:
        refreshed = await session.get(Job, job_id)
        assert refreshed is not None
        assert refreshed.status == JobStatus.FAILED
        assert refreshed.error_message == "worker restarted"
        assert refreshed.finished_at is not None


@pytest.mark.asyncio
async def test_process_job_success_marks_succeeded_and_persists_logs(
    fake_redis, monkeypatch
):
    job = await _create_queued_job()
    monkeypatch.setattr(
        "worker.agent.run_container",
        lambda spec, job_id, timeout_seconds, cancel_event=None: ContainerRunResult(
            exit_code=0,
            error_message=None,
            log_tail="ok\n",
        ),
    )

    await process_job(str(job.id), "test-worker", fake_redis)

    async with database.SessionLocal() as session:
        refreshed = await session.get(Job, job.id)
        assert refreshed is not None
        assert refreshed.status == JobStatus.SUCCEEDED
        assert refreshed.exit_code == 0
        assert refreshed.worker_id == "test-worker"
        assert refreshed.finished_at is not None

        logs = await session.execute(select(JobLog).where(JobLog.job_id == job.id))
        log_row = logs.scalar_one()
        assert log_row.content == "ok\n"


@pytest.mark.asyncio
async def test_process_job_nonzero_exit_marks_failed(fake_redis, monkeypatch):
    job = await _create_queued_job(name="fail-job")
    monkeypatch.setattr(
        "worker.agent.run_container",
        lambda spec, job_id, timeout_seconds, cancel_event=None: ContainerRunResult(
            exit_code=7,
            error_message=None,
            log_tail="boom\n",
        ),
    )

    await process_job(str(job.id), "test-worker", fake_redis)

    async with database.SessionLocal() as session:
        refreshed = await session.get(Job, job.id)
        assert refreshed is not None
        assert refreshed.status == JobStatus.FAILED
        assert refreshed.exit_code == 7


@pytest.mark.asyncio
async def test_process_job_timeout_marks_failed(fake_redis, monkeypatch):
    job = await _create_queued_job(name="timeout-job")
    monkeypatch.setattr(
        "worker.agent.run_container",
        lambda spec, job_id, timeout_seconds, cancel_event=None: ContainerRunResult(
            exit_code=None,
            error_message="timeout",
            log_tail="",
            timed_out=True,
        ),
    )

    await process_job(str(job.id), "test-worker", fake_redis)

    async with database.SessionLocal() as session:
        refreshed = await session.get(Job, job.id)
        assert refreshed is not None
        assert refreshed.status == JobStatus.FAILED
        assert refreshed.error_message == "timeout"


@pytest.mark.asyncio
async def test_process_job_skips_non_queued_job(fake_redis, monkeypatch):
    job = await _create_queued_job(name="already-running")
    async with database.SessionLocal() as session:
        db_job = await session.get(Job, job.id)
        assert db_job is not None
        db_job.status = JobStatus.RUNNING
        await session.commit()

    run_mock = MagicMock()
    monkeypatch.setattr("worker.agent.run_container", run_mock)

    await process_job(str(job.id), "test-worker", fake_redis)
    run_mock.assert_not_called()


@pytest.mark.asyncio
async def test_worker_redis_socket_timeout_exceeds_brpop_timeout():
    redis = _worker_redis()
    try:
        assert redis.connection_pool.connection_kwargs["socket_timeout"] > 5
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_worker_lock_allows_single_holder(fake_redis):
    lock_a = WorkerLock(fake_redis, "node-a")
    lock_b = WorkerLock(fake_redis, "node-a")

    assert await lock_a.acquire() is True
    assert await lock_b.acquire() is False

    await lock_a.release()
    assert await lock_b.acquire() is True
    await lock_b.release()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_run_container_with_real_docker(monkeypatch):
    docker = pytest.importorskip("docker")
    client = docker.from_env()
    try:
        client.ping()
    except Exception as exc:
        pytest.skip(f"Docker daemon unavailable: {exc}")

    from worker.container import run_container

    spec = JobSpec.model_validate(_job_spec())
    result = run_container(spec, str(uuid.uuid4()), timeout_seconds=60)
    assert result.exit_code == 0
    assert "ok" in result.log_tail
