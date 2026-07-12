"""Story A1 acceptance tests — admin-managed accounts."""
import pytest
from httpx import AsyncClient

from api.models import User
from tests.conftest import auth_header, create_api_key, login


@pytest.mark.asyncio
async def test_admin_creates_user_with_temporary_password(client: AsyncClient, admin_user: User):
    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    response = await client.post(
        "/api/v1/admin/users",
        headers=auth_header(admin_tokens["access_token"]),
        json={"email": "newuser@example.com", "role": "user"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "newuser@example.com"
    assert body["must_change_password"] is True
    assert "temporary_password" in body
    assert len(body["temporary_password"]) >= 12
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_admin_create_user_duplicate_email_returns_409(
    client: AsyncClient, admin_user: User, test_user: User
):
    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    response = await client.post(
        "/api/v1/admin/users",
        headers=auth_header(admin_tokens["access_token"]),
        json={"email": test_user.email, "role": "user"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_admin_list_users_is_paginated_and_hides_hashes(
    client: AsyncClient, admin_user: User, test_user: User
):
    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    response = await client.get(
        "/api/v1/admin/users?limit=10&offset=0",
        headers=auth_header(admin_tokens["access_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    assert len(body["items"]) >= 2
    for item in body["items"]:
        assert "password_hash" not in item
        assert set(item.keys()) >= {
            "id",
            "email",
            "role",
            "created_at",
            "must_change_password",
            "disabled",
        }


@pytest.mark.asyncio
async def test_temp_password_login_blocks_other_routes_until_password_change(
    client: AsyncClient, admin_user: User
):
    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    created = await client.post(
        "/api/v1/admin/users",
        headers=auth_header(admin_tokens["access_token"]),
        json={"email": "temp@example.com", "role": "user"},
    )
    temp_password = created.json()["temporary_password"]

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "temp@example.com", "password": temp_password},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    blocked = await client.get("/api/v1/keys", headers=auth_header(access_token))
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "password change required"

    change_response = await client.post(
        "/api/v1/auth/change-password",
        headers=auth_header(access_token),
        json={
            "old_password": temp_password,
            "new_password": "new-secure-password",
        },
    )
    assert change_response.status_code == 204

    allowed = await client.get("/api/v1/keys", headers=auth_header(access_token))
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_short_new_password(
    client: AsyncClient, admin_user: User
):
    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    created = await client.post(
        "/api/v1/admin/users",
        headers=auth_header(admin_tokens["access_token"]),
        json={"email": "shortpw@example.com", "role": "user"},
    )
    temp_password = created.json()["temporary_password"]
    user_tokens = await login(client, "shortpw@example.com", temp_password)

    response = await client.post(
        "/api/v1/auth/change-password",
        headers=auth_header(user_tokens["access_token"]),
        json={"old_password": temp_password, "new_password": "short"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_disabled_user_jwt_and_api_key_both_fail(
    client: AsyncClient, admin_user: User, test_user: User
):
    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    user_tokens = await login(client, test_user.email, "correct-password-12")
    api_key = await create_api_key(
        client, user_tokens["access_token"], name="disabled-key", scopes=["jobs:read"]
    )

    disable_response = await client.delete(
        f"/api/v1/admin/users/{test_user.id}",
        headers=auth_header(admin_tokens["access_token"]),
    )
    assert disable_response.status_code == 204

    jwt_probe = await client.get("/api/v1/auth/me", headers=auth_header(user_tokens["access_token"]))
    assert jwt_probe.status_code == 401

    key_probe = await client.get(
        "/api/v1/test/scope-probe/jobs-read",
        headers=auth_header(api_key),
    )
    assert key_probe.status_code == 401

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "correct-password-12"},
    )
    assert login_response.status_code == 401


@pytest.mark.asyncio
async def test_admin_cannot_disable_self(client: AsyncClient, admin_user: User):
    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    response = await client.delete(
        f"/api/v1/admin/users/{admin_user.id}",
        headers=auth_header(admin_tokens["access_token"]),
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_non_admin_cannot_create_users(client: AsyncClient, test_user: User):
    user_tokens = await login(client, test_user.email, "correct-password-12")
    response = await client.post(
        "/api/v1/admin/users",
        headers=auth_header(user_tokens["access_token"]),
        json={"email": "blocked@example.com", "role": "user"},
    )
    assert response.status_code == 403
