"""Story E2 acceptance tests — Redis token-bucket rate limiting."""
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from api.config import settings
from api.database import get_db
from api.main import app
from api.models import User
from api.queue import get_redis, set_redis_client
from tests.conftest import auth_header, create_api_key, login


@pytest.mark.asyncio
async def test_burst_then_429_with_headers(client: AsyncClient, test_user: User, monkeypatch):
    # Near-zero refill so sequential requests don't top the bucket back up mid-test.
    monkeypatch.setattr(settings, "rate_limit_default_burst", 3)
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 1)

    tokens = await login(client, test_user.email, "correct-password-12")
    headers = auth_header(tokens["access_token"])

    for _ in range(3):
        response = await client.get("/api/v1/jobs", headers=headers)
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert int(response.headers["X-RateLimit-Limit"]) == 3

    blocked = await client.get("/api/v1/jobs", headers=headers)
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Rate limit exceeded"
    assert "Retry-After" in blocked.headers
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.headers["X-RateLimit-Limit"] == "3"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in blocked.headers


@pytest.mark.asyncio
async def test_healthz_is_exempt(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_default_burst", 1)
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 1)

    for _ in range(5):
        response = await client.get("/api/v1/healthz")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers


@pytest.mark.asyncio
async def test_auth_route_stricter_than_general(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_auth_burst", 2)
    monkeypatch.setattr(settings, "rate_limit_auth_per_min", 1)
    monkeypatch.setattr(settings, "rate_limit_default_burst", 90)
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 60)

    body = {"email": "nobody@example.com", "password": "wrong-password-12"}
    first = await client.post("/api/v1/auth/login", json=body)
    second = await client.post("/api/v1/auth/login", json=body)
    assert first.status_code == 401
    assert second.status_code == 401

    third = await client.post("/api/v1/auth/login", json=body)
    assert third.status_code == 429
    assert "Retry-After" in third.headers


@pytest.mark.asyncio
async def test_api_key_identity_isolation(client: AsyncClient, test_user: User, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_default_burst", 2)
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 1)

    tokens = await login(client, test_user.email, "correct-password-12")
    key_a = await create_api_key(
        client, tokens["access_token"], name="key-a", scopes=["jobs:read"]
    )
    key_b = await create_api_key(
        client, tokens["access_token"], name="key-b", scopes=["jobs:read"]
    )

    for _ in range(2):
        assert (await client.get("/api/v1/jobs", headers=auth_header(key_a))).status_code == 200
    blocked_a = await client.get("/api/v1/jobs", headers=auth_header(key_a))
    assert blocked_a.status_code == 429

    # Key B has its own bucket and can still succeed.
    ok_b = await client.get("/api/v1/jobs", headers=auth_header(key_b))
    assert ok_b.status_code == 200


@pytest.mark.asyncio
async def test_lua_atomicity_under_concurrent_hits(
    client: AsyncClient, test_user: User, monkeypatch
):
    monkeypatch.setattr(settings, "rate_limit_default_burst", 10)
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 1)

    tokens = await login(client, test_user.email, "correct-password-12")
    headers = auth_header(tokens["access_token"])

    async def hit() -> int:
        response = await client.get("/api/v1/jobs", headers=headers)
        return response.status_code

    statuses = await asyncio.gather(*[hit() for _ in range(40)])
    allowed = sum(1 for code in statuses if code == 200)
    denied = sum(1 for code in statuses if code == 429)
    assert allowed == 10
    assert denied == 30
    assert allowed + denied == 40


@pytest.mark.asyncio
async def test_fail_open_on_redis_outage(fake_redis, test_user: User):
    class BrokenRedis:
        async def evalsha(self, *args, **kwargs):
            raise ConnectionError("redis down")

        async def script_load(self, *args, **kwargs):
            raise ConnectionError("redis down")

    async def override_get_db():
        import api.database as database

        async with database.SessionLocal() as session:
            yield session

    async def override_get_redis():
        yield BrokenRedis()

    app.state.redis = BrokenRedis()
    app.state.rate_limit_script_sha = "deadbeef"
    set_redis_client(None)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": test_user.email, "password": "correct-password-12"},
            )
            assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
        set_redis_client(None)
        app.state.redis = None
        app.state.rate_limit_script_sha = None
