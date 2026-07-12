"""Story A2 acceptance tests — login & session security."""
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from api.config import settings
from api.deps import get_current_admin
from api.models import User
from api.routers.auth import REFRESH_COOKIE
from api.security import decode_access_token
from tests.conftest import login


@pytest.mark.asyncio
async def test_login_success_returns_jwt_and_httponly_refresh_cookie(
    client: AsyncClient, test_user: User
):
    """JWT access (15 min) + rotating refresh token in httpOnly cookie."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "correct-password-12"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body

    payload = decode_access_token(body["access_token"])
    assert payload["sub"] == str(test_user.id)
    assert payload["role"] == test_user.role.value
    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    iat = datetime.fromtimestamp(payload["iat"], tz=UTC)
    assert exp - iat == timedelta(minutes=settings.jwt_access_ttl_minutes)

    assert REFRESH_COOKIE in response.cookies
    set_cookie = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()


@pytest.mark.asyncio
async def test_login_wrong_email_and_wrong_password_share_same_message(
    client: AsyncClient, test_user: User
):
    wrong_email = await client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "correct-password-12"},
    )
    wrong_password = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "wrong-password-12"},
    )
    assert wrong_email.status_code == 401
    assert wrong_password.status_code == 401
    assert wrong_email.json()["detail"] == wrong_password.json()["detail"]


@pytest.mark.asyncio
async def test_login_rejects_unknown_fields(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "correct-password-12",
            "extra": "nope",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_cookie_and_issues_new_access_token(
    client: AsyncClient, test_user: User
):
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "correct-password-12"},
    )
    first_refresh = login_response.cookies[REFRESH_COOKIE]

    refresh_response = await client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    second_refresh = refresh_response.cookies[REFRESH_COOKIE]

    assert second_refresh != first_refresh
    assert "access_token" in refresh_response.json()


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_entire_token_family(client: AsyncClient, test_user: User):
    """If a revoked refresh token is replayed, revoke the whole family."""
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "correct-password-12"},
    )
    stolen_refresh = login_response.cookies[REFRESH_COOKIE]

    rotate_response = await client.post("/api/v1/auth/refresh")
    assert rotate_response.status_code == 200
    current_refresh = rotate_response.cookies[REFRESH_COOKIE]

    reuse_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={REFRESH_COOKIE: stolen_refresh},
    )
    assert reuse_response.status_code == 401

    current_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={REFRESH_COOKIE: current_refresh},
    )
    assert current_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_family_and_clears_cookie(client: AsyncClient, test_user: User):
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "correct-password-12"},
    )
    refresh_cookie = login_response.cookies[REFRESH_COOKIE]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        cookies={REFRESH_COOKIE: refresh_cookie},
    )
    assert logout_response.status_code == 204

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={REFRESH_COOKIE: refresh_cookie},
    )
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_accepts_valid_access_token(client: AsyncClient, test_user: User):
    tokens = await login(client, test_user.email, "correct-password-12")
    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    body = me_response.json()
    assert body["email"] == test_user.email
    assert body["role"] == test_user.role.value


@pytest.mark.asyncio
async def test_get_current_user_rejects_invalid_access_token(client: AsyncClient):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_admin_requires_admin_role(admin_user: User, test_user: User):
    await get_current_admin(admin_user)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_admin(test_user)
    assert exc_info.value.status_code == 403
