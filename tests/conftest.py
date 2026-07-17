"""Shared pytest fixtures for API integration tests."""
from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import api.database as database
from api.config import settings
from api.database import Base, get_db
from api.main import app
from api.models import User, UserRole
from api.queue import get_redis, set_redis_client
from api.rate_limit import register_script
from api.security import hash_password

_TRUNCATE_SQL = (
    "TRUNCATE job_logs, jobs, api_keys, refresh_tokens, quotas, users "
    "RESTART IDENTITY CASCADE"
)


@pytest.fixture(scope="session", autouse=True)
async def configure_test_database() -> AsyncGenerator[None, None]:
    test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    database.engine = test_engine
    database.SessionLocal = test_session_factory

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await test_engine.dispose()


@pytest.fixture(autouse=True)
async def clean_auth_tables() -> AsyncGenerator[None, None]:
    # AUTOCOMMIT so TRUNCATE is visible immediately to subsequent fixture inserts,
    # even if a previous request left an aborted transaction on another connection.
    async with database.engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(_TRUNCATE_SQL))
    yield


@pytest.fixture(autouse=True)
def generous_rate_limits(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep production-like limits only in E2 tests; elsewhere avoid cross-test 429 noise."""
    if request.node.path.name == "test_rate_limit.py":
        return
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 10_000)
    monkeypatch.setattr(settings, "rate_limit_default_burst", 10_000)
    monkeypatch.setattr(settings, "rate_limit_auth_per_min", 10_000)
    monkeypatch.setattr(settings, "rate_limit_auth_burst", 10_000)
    monkeypatch.setattr(settings, "rate_limit_jobs_write_per_hour", 10_000)
    monkeypatch.setattr(settings, "rate_limit_jobs_write_burst", 10_000)
    monkeypatch.setattr(settings, "rate_limit_llm_per_min", 10_000)
    monkeypatch.setattr(settings, "rate_limit_llm_burst", 10_000)


@pytest.fixture
async def fake_redis() -> AsyncGenerator[Redis, None]:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
async def client(
    fake_redis: Redis,
    clean_auth_tables: None,
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with database.SessionLocal() as session:
            yield session

    async def override_get_redis() -> AsyncGenerator[Redis, None]:
        yield fake_redis

    script_sha = await register_script(fake_redis)
    app.state.redis = fake_redis
    app.state.rate_limit_script_sha = script_sha
    set_redis_client(fake_redis)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
    set_redis_client(None)
    app.state.redis = None
    app.state.rate_limit_script_sha = None


@pytest.fixture
async def test_user(clean_auth_tables: None) -> User:
    async with database.SessionLocal() as session:
        user = User(
            email="user@example.com",
            password_hash=hash_password("correct-password-12"),
            role=UserRole.user,
            must_change_password=False,
        )
        session.add(user)
        await session.flush()
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def other_user(clean_auth_tables: None) -> User:
    async with database.SessionLocal() as session:
        user = User(
            email="other@example.com",
            password_hash=hash_password("other-password-12"),
            role=UserRole.user,
            must_change_password=False,
        )
        session.add(user)
        await session.flush()
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def admin_user(clean_auth_tables: None) -> User:
    async with database.SessionLocal() as session:
        user = User(
            email="admin@example.com",
            password_hash=hash_password("admin-password-12"),
            role=UserRole.admin,
            must_change_password=False,
        )
        session.add(user)
        await session.flush()
        await session.commit()
        await session.refresh(user)
        return user


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(client: AsyncClient, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def create_api_key(
    client: AsyncClient,
    access_token: str,
    *,
    name: str,
    scopes: list[str],
    expires_at: str | None = None,
) -> str:
    payload: dict = {"name": name, "scopes": scopes}
    if expires_at is not None:
        payload["expires_at"] = expires_at

    response = await client.post(
        "/api/v1/keys",
        headers=auth_header(access_token),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()["store_this_now"]
