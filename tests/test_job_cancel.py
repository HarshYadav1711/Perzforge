"""Story B5 acceptance tests — job cancellation."""
import asyncio
import time
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

import api.database as database
from api.job_control import job_control_channel
from api.models import Job, JobStatus, User, UserRole
from api.security import hash_password
from tests.conftest import auth_header, login
from worker.agent import process_job
from worker.container import ContainerRunResult
from worker.repository import reap_zombie_jobs


def _job_spec() -> dict:
    return {
        "image": "python:3.12-alpine",
        "command": ["python", "-c", "import time; time.sleep(30)"],
        "env": {},
        "gpu": False,
        "timeout_minutes": 60,
    }


async def _create_job(
    user_id: uuid.UUID,
    *,
    status: JobStatus = JobStatus.QUEUED,
    worker_id: str | None = None,
) -> Job:
    async with database.SessionLocal() as session:
        job = Job(
            user_id=user_id,
            name="cancel-test",
            spec=_job_spec(),
            status=status,
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC) if status in {JobStatus.RUNNING, JobStatus.CANCELLING} else None,
            worker_id=worker_id,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


@pytest.mark.asyncio
async def test_cancel_queued_job_sets_cancelled(client: AsyncClient, test_user: User):
    tokens = await login(client, test_user.email, "correct-password-12")
    create_response = await client.post(
        "/api/v1/jobs",
        headers=auth_header(tokens["access_token"]),
        json={"name": "queued-cancel", "spec": _job_spec()},
    )
    job_id = create_response.json()["id"]

    response = await client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CANCELLED"
    assert body["finished_at"] is not None


@pytest.mark.asyncio
async def test_cancel_running_job_sets_cancelling_and_publishes_control(
    client: AsyncClient, test_user: User, fake_redis
):
    job = await _create_job(test_user.id, status=JobStatus.RUNNING, worker_id="test-worker")
    tokens = await login(client, test_user.email, "correct-password-12")

    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(job_control_channel(str(job.id)))
    await pubsub.get_message(timeout=1)

    response = await client.post(
        f"/api/v1/jobs/{job.id}/cancel",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLING"

    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    await pubsub.unsubscribe(job_control_channel(str(job.id)))
    await pubsub.aclose()
    assert message is not None
    assert message["data"] == '{"cmd": "cancel"}'


@pytest.mark.asyncio
async def test_cancel_running_reaches_cancelled_within_12_seconds(
    fake_redis, test_user: User, monkeypatch
):
    job = await _create_job(test_user.id, status=JobStatus.QUEUED)

    def slow_run(spec, job_id, timeout_seconds, cancel_event=None):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                return ContainerRunResult(
                    exit_code=None,
                    error_message=None,
                    log_tail="partial\n",
                    cancelled=True,
                )
            time.sleep(0.05)
        return ContainerRunResult(exit_code=0, error_message=None, log_tail="done\n")

    monkeypatch.setattr("worker.agent.run_container", slow_run)

    task = asyncio.create_task(process_job(str(job.id), "test-worker", fake_redis))

    running = False
    for _ in range(100):
        async with database.SessionLocal() as session:
            refreshed = await session.get(Job, job.id)
            if refreshed is not None and refreshed.status == JobStatus.RUNNING:
                running = True
                break
        await asyncio.sleep(0.05)
    assert running, "job never reached RUNNING"

    await asyncio.sleep(0.3)
    await fake_redis.publish(job_control_channel(str(job.id)), '{"cmd": "cancel"}')

    await asyncio.wait_for(task, timeout=12)

    async with database.SessionLocal() as session:
        refreshed = await session.get(Job, job.id)
        assert refreshed is not None
        assert refreshed.status == JobStatus.CANCELLED
        assert refreshed.finished_at is not None


@pytest.mark.asyncio
async def test_double_cancel_returns_409(client: AsyncClient, test_user: User):
    job = await _create_job(test_user.id, status=JobStatus.CANCELLED)
    tokens = await login(client, test_user.email, "correct-password-12")

    response = await client.post(
        f"/api/v1/jobs/{job.id}/cancel",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "job already finished"


@pytest.mark.asyncio
async def test_cancel_cancelling_job_returns_409(client: AsyncClient, test_user: User):
    job = await _create_job(test_user.id, status=JobStatus.CANCELLING, worker_id="test-worker")
    tokens = await login(client, test_user.email, "correct-password-12")

    response = await client.post(
        f"/api/v1/jobs/{job.id}/cancel",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "job already finished"


@pytest.mark.asyncio
async def test_cancel_foreign_job_returns_404(
    client: AsyncClient, test_user: User, other_user: User
):
    job = await _create_job(other_user.id, status=JobStatus.QUEUED)
    tokens = await login(client, test_user.email, "correct-password-12")

    response = await client.post(
        f"/api/v1/jobs/{job.id}/cancel",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reaper_converts_orphaned_cancelling_to_cancelled(fake_redis):
    hostname = "test-worker"
    async with database.SessionLocal() as session:
        user = User(
            email="cancelling-zombie@example.com",
            password_hash=hash_password("correct-password-12"),
            role=UserRole.user,
            must_change_password=False,
        )
        session.add(user)
        await session.flush()
        job = Job(
            user_id=user.id,
            name="cancelling-zombie",
            spec=_job_spec(),
            status=JobStatus.CANCELLING,
            worker_id=hostname,
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    reaped = await reap_zombie_jobs(hostname)
    assert reaped == 1

    async with database.SessionLocal() as session:
        refreshed = await session.get(Job, job_id)
        assert refreshed is not None
        assert refreshed.status == JobStatus.CANCELLED
        assert refreshed.finished_at is not None
        assert refreshed.error_message is None
