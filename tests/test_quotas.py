"""Story E1 acceptance tests — quota engine."""
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import api.database as database
from api.config import settings
from api.models import Quota, User
from api.quotas import QuotaResource, get_or_create_quota, quota_counter_key
from tests.conftest import auth_header, login


def valid_job_payload(name: str = "train-cnn") -> dict:
    return {
        "name": name,
        "spec": {
            "image": "python:3.12-slim",
            "command": ["python", "train.py"],
            "env": {},
            "gpu": False,
            "timeout_minutes": 60,
        },
    }


@pytest.mark.asyncio
async def test_quota_row_lazily_created_on_first_check(client: AsyncClient, test_user: User):
    tokens = await login(client, test_user.email, "correct-password-12")

    async with database.SessionLocal() as session:
        before = await session.execute(select(Quota).where(Quota.user_id == test_user.id))
        assert before.scalar_one_or_none() is None

    response = await client.get(
        "/api/v1/me/quota",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["limits"]["max_concurrent_jobs"] == settings.max_concurrent_jobs_per_user
    assert body["limits"]["max_jobs_per_day"] == settings.max_jobs_per_day_per_user
    assert body["usage"]["max_concurrent_jobs"]["current"] == 0
    assert body["usage"]["max_jobs_per_day"]["current"] == 0

    async with database.SessionLocal() as session:
        after = await session.execute(select(Quota).where(Quota.user_id == test_user.id))
        assert after.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_over_concurrent_blocked_with_named_limit(
    client: AsyncClient, test_user: User, fake_redis
):
    tokens = await login(client, test_user.email, "correct-password-12")
    headers = auth_header(tokens["access_token"])
    limit = settings.max_concurrent_jobs_per_user

    for index in range(limit):
        response = await client.post(
            "/api/v1/jobs",
            headers=headers,
            json=valid_job_payload(name=f"job-{index}"),
        )
        assert response.status_code == 201

    over_cap = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json=valid_job_payload(name="one-too-many"),
    )
    assert over_cap.status_code == 429
    body = over_cap.json()
    assert body["quota"] == "max_concurrent_jobs"
    assert body["limit"] == limit
    assert body["current"] == limit
    assert "max_concurrent_jobs" in body["detail"]


@pytest.mark.asyncio
async def test_daily_job_counter_increments_and_expires(
    client: AsyncClient, test_user: User, fake_redis
):
    tokens = await login(client, test_user.email, "correct-password-12")
    headers = auth_header(tokens["access_token"])

    response = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json=valid_job_payload(name="daily-1"),
    )
    assert response.status_code == 201

    key = quota_counter_key(test_user.id, QuotaResource.JOBS_PER_DAY)
    assert int(await fake_redis.get(key) or 0) == 1
    ttl = await fake_redis.ttl(key)
    assert ttl > 0
    assert ttl <= settings.quota_counter_ttl_seconds

    day = datetime.now(UTC).strftime("%Y%m%d")
    assert day in key


@pytest.mark.asyncio
async def test_daily_quota_blocks_when_exhausted(
    client: AsyncClient, test_user: User, fake_redis
):
    tokens = await login(client, test_user.email, "correct-password-12")
    headers = auth_header(tokens["access_token"])

    async with database.SessionLocal() as session:
        user = await session.get(User, test_user.id)
        assert user is not None
        quota = await get_or_create_quota(session, user)
        quota.max_jobs_per_day = 1
        quota.max_concurrent_jobs = 10
        await session.commit()

    first = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json=valid_job_payload(name="allowed"),
    )
    assert first.status_code == 201

    blocked = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json=valid_job_payload(name="blocked"),
    )
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["quota"] == "max_jobs_per_day"
    assert body["limit"] == 1
    assert body["current"] == 1


@pytest.mark.asyncio
async def test_admin_quota_override_takes_effect_immediately(
    client: AsyncClient, test_user: User, admin_user: User, fake_redis
):
    user_tokens = await login(client, test_user.email, "correct-password-12")
    admin_tokens = await login(client, admin_user.email, "admin-password-12")

    patch = await client.patch(
        f"/api/v1/admin/users/{test_user.id}/quota",
        headers=auth_header(admin_tokens["access_token"]),
        json={"max_concurrent_jobs": 1},
    )
    assert patch.status_code == 200
    assert patch.json()["max_concurrent_jobs"] == 1

    headers = auth_header(user_tokens["access_token"])
    first = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json=valid_job_payload(name="only-one"),
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json=valid_job_payload(name="blocked"),
    )
    assert second.status_code == 429
    assert second.json()["quota"] == "max_concurrent_jobs"
    assert second.json()["limit"] == 1


@pytest.mark.asyncio
async def test_admin_patch_foreign_missing_user_returns_404(
    client: AsyncClient, admin_user: User
):
    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    response = await client.patch(
        "/api/v1/admin/users/00000000-0000-0000-0000-000000000099/quota",
        headers=auth_header(admin_tokens["access_token"]),
        json={"max_instances": 3},
    )
    assert response.status_code == 404
