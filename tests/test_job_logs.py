"""Story B2 acceptance tests — live job log WebSocket streaming."""
import concurrent.futures
import threading
import uuid
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import api.database as database
from api.database import get_db
from api.log_stream import eof_message, job_log_buffer_key, job_log_channel
from api.main import app
from api.models import Job, JobLog, JobStatus, User
from api.queue import get_redis
from tests.conftest import auth_header


def _login_sync(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


async def _login(client: TestClient, email: str, password: str) -> dict:
    return _login_sync(client, email, password)


async def _create_api_key(
    client: TestClient, access_token: str, *, name: str, scopes: list[str]
) -> str:
    response = client.post(
        "/api/v1/keys",
        headers=auth_header(access_token),
        json={"name": name, "scopes": scopes},
    )
    assert response.status_code == 201
    return response.json()["store_this_now"]


def _job_spec() -> dict:
    return {
        "image": "python:3.12-alpine",
        "command": ["python", "-c", "print('ok')"],
        "env": {},
        "gpu": False,
        "timeout_minutes": 60,
    }


async def _create_job(
    user_id: uuid.UUID,
    *,
    status: JobStatus = JobStatus.RUNNING,
    log_content: str | None = None,
) -> Job:
    async with database.SessionLocal() as session:
        job = Job(
            user_id=user_id,
            name="log-test",
            spec=_job_spec(),
            status=status,
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC) if status == JobStatus.RUNNING else None,
            finished_at=datetime.now(UTC)
            if status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
            else None,
        )
        session.add(job)
        await session.flush()
        if log_content is not None:
            session.add(JobLog(job_id=job.id, content=log_content))
        await session.commit()
        await session.refresh(job)
        return job


@pytest.fixture
async def ws_client(fake_redis, clean_auth_tables) -> TestClient:
    async def override_get_db():
        async with database.SessionLocal() as session:
            yield session

    async def override_get_redis():
        yield fake_redis

    from api.queue import set_redis_client
    from api.rate_limit import register_script

    script_sha = await register_script(fake_redis)
    app.state.redis = fake_redis
    app.state.rate_limit_script_sha = script_sha
    set_redis_client(fake_redis)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    set_redis_client(None)
    app.state.redis = None
    app.state.rate_limit_script_sha = None


@pytest.mark.asyncio
async def test_ws_rejects_unauthenticated_before_accept(ws_client: TestClient, test_user: User):
    job = await _create_job(test_user.id)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(f"/api/v1/jobs/{job.id}/logs"):
            pass
    assert exc_info.value.code == 4401


@pytest.mark.asyncio
async def test_ws_rejects_foreign_job_with_4404(
    ws_client: TestClient, test_user: User, other_user: User
):
    job = await _create_job(other_user.id)
    tokens = await _login(ws_client, test_user.email, "correct-password-12")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(
            f"/api/v1/jobs/{job.id}/logs?token={tokens['access_token']}"
        ):
            pass
    assert exc_info.value.code == 4404


@pytest.mark.asyncio
async def test_ws_rejects_api_key_without_jobs_read_scope(
    ws_client: TestClient, test_user: User
):
    job = await _create_job(test_user.id)
    tokens = await _login(ws_client, test_user.email, "correct-password-12")
    api_key = await _create_api_key(
        ws_client,
        tokens["access_token"],
        name="no-read",
        scopes=["jobs:write"],
    )
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(f"/api/v1/jobs/{job.id}/logs?token={api_key}"):
            pass
    assert exc_info.value.code == 4403


@pytest.mark.asyncio
async def test_ws_finished_job_replays_persisted_logs_and_closes(
    ws_client: TestClient, test_user: User
):
    job = await _create_job(
        test_user.id,
        status=JobStatus.SUCCEEDED,
        log_content="done\nsecond line\n",
    )
    tokens = await _login(ws_client, test_user.email, "correct-password-12")
    with ws_client.websocket_connect(
        f"/api/v1/jobs/{job.id}/logs?token={tokens['access_token']}"
    ) as ws:
        assert ws.receive_text() == "done\nsecond line\n"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()


@pytest.mark.asyncio
async def test_ws_replays_history_and_relays_live_until_eof(
    ws_client: TestClient, test_user: User, fake_redis
):
    job = await _create_job(test_user.id, status=JobStatus.RUNNING)
    job_id = str(job.id)
    buffer_key = job_log_buffer_key(job_id)
    channel = job_log_channel(job_id)
    await fake_redis.rpush(buffer_key, "history line\n")

    tokens = await _login(ws_client, test_user.email, "correct-password-12")
    token = tokens["access_token"]
    subscribed = threading.Event()

    def consume_ws() -> list:
        messages: list = []
        with ws_client.websocket_connect(f"/api/v1/jobs/{job.id}/logs?token={token}") as ws:
            messages.append(ws.receive_text())
            subscribed.set()
            messages.append(ws.receive_text())
            messages.append(ws.receive_json())
        return messages

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(consume_ws)
        assert subscribed.wait(timeout=5)
        await fake_redis.publish(channel, "live line\n")
        await fake_redis.publish(channel, eof_message(0))
        messages = future.result(timeout=5)

    assert messages[0] == "history line\n"
    assert messages[1] == "live line\n"
    assert messages[2] == {"event": "eof", "exit_code": 0}


@pytest.mark.asyncio
async def test_ws_eof_sentinel_closes_cleanly(ws_client: TestClient, test_user: User, fake_redis):
    job = await _create_job(test_user.id, status=JobStatus.RUNNING)
    channel = job_log_channel(str(job.id))
    tokens = await _login(ws_client, test_user.email, "correct-password-12")
    subscribed = threading.Event()

    def consume_ws() -> dict:
        with ws_client.websocket_connect(
            f"/api/v1/jobs/{job.id}/logs?token={tokens['access_token']}"
        ) as ws:
            subscribed.set()
            return ws.receive_json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(consume_ws)
        assert subscribed.wait(timeout=5)
        await fake_redis.publish(channel, eof_message(7))
        eof = future.result(timeout=5)

    assert eof == {"event": "eof", "exit_code": 7}
