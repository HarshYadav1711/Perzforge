"""Shared pytest fixtures for API integration tests."""
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import api.database as database
from api.config import settings
from api.database import Base, get_db
from api.main import app
from api.models import ApiKey, RefreshToken, User, UserRole
from api.security import hash_password


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
    async with database.SessionLocal() as session:
        await session.execute(delete(ApiKey))
        await session.execute(delete(RefreshToken))
        await session.execute(delete(User))
        await session.commit()
    yield


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with database.SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def test_user() -> User:
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
        return user


@pytest.fixture
async def other_user() -> User:
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
        return user


@pytest.fixture
async def admin_user() -> User:
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
        return user


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(client: AsyncClient, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
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
    assert response.status_code == 201
    return response.json()["store_this_now"]
