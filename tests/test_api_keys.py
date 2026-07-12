"""Story A3 acceptance tests — scoped API keys."""
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, create_api_key, login


@pytest.mark.asyncio
async def test_create_key_returns_plaintext_once(client: AsyncClient, test_user):
    tokens = await login(client, test_user.email, "correct-password-12")
    response = await client.post(
        "/api/v1/keys",
        headers=auth_header(tokens["access_token"]),
        json={"name": "ci-bot", "scopes": ["jobs:read", "jobs:write"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["store_this_now"].startswith("pzf_")
    assert body["prefix"] == body["store_this_now"][:8]
    assert "key_hash" not in body
    assert body["scopes"] == ["jobs:read", "jobs:write"]


@pytest.mark.asyncio
async def test_list_keys_never_leaks_hash_material(client: AsyncClient, test_user):
    tokens = await login(client, test_user.email, "correct-password-12")
    create_response = await client.post(
        "/api/v1/keys",
        headers=auth_header(tokens["access_token"]),
        json={"name": "listable", "scopes": ["jobs:read"]},
    )
    assert create_response.status_code == 201

    list_response = await client.get(
        "/api/v1/keys",
        headers=auth_header(tokens["access_token"]),
    )
    assert list_response.status_code == 200
    keys = list_response.json()
    assert len(keys) == 1
    item = keys[0]
    assert set(item.keys()) == {
        "id",
        "name",
        "prefix",
        "scopes",
        "rate_limit_tier",
        "expires_at",
        "revoked",
        "last_used_at",
        "created_at",
    }
    assert "store_this_now" not in item
    assert "key_hash" not in item


@pytest.mark.asyncio
async def test_revoked_key_fails_on_next_request(client: AsyncClient, test_user):
    tokens = await login(client, test_user.email, "correct-password-12")
    plaintext = await create_api_key(
        client, tokens["access_token"], name="revoke-me", scopes=["jobs:read"]
    )

    probe_before = await client.get(
        "/api/v1/test/scope-probe/jobs-read",
        headers=auth_header(plaintext),
    )
    assert probe_before.status_code == 200

    key_id = (
        await client.get("/api/v1/keys", headers=auth_header(tokens["access_token"]))
    ).json()[0]["id"]

    revoke_response = await client.delete(
        f"/api/v1/keys/{key_id}",
        headers=auth_header(tokens["access_token"]),
    )
    assert revoke_response.status_code == 204

    probe_after = await client.get(
        "/api/v1/test/scope-probe/jobs-read",
        headers=auth_header(plaintext),
    )
    assert probe_after.status_code == 401


@pytest.mark.asyncio
async def test_scope_enforcement_denies_missing_scope(client: AsyncClient, test_user):
    tokens = await login(client, test_user.email, "correct-password-12")
    plaintext = await create_api_key(
        client, tokens["access_token"], name="read-only", scopes=["jobs:read"]
    )

    allowed = await client.get(
        "/api/v1/test/scope-probe/jobs-read",
        headers=auth_header(plaintext),
    )
    assert allowed.status_code == 200

    denied = await client.post(
        "/api/v1/test/scope-probe/jobs-write",
        headers=auth_header(plaintext),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Insufficient scope"


@pytest.mark.asyncio
async def test_expired_key_is_rejected(client: AsyncClient, test_user):
    tokens = await login(client, test_user.email, "correct-password-12")
    expired_at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    plaintext = await create_api_key(
        client,
        tokens["access_token"],
        name="expired",
        scopes=["jobs:read"],
        expires_at=expired_at,
    )

    response = await client.get(
        "/api/v1/test/scope-probe/jobs-read",
        headers=auth_header(plaintext),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_foreign_key_returns_404(client: AsyncClient, test_user, other_user):
    owner_tokens = await login(client, test_user.email, "correct-password-12")
    other_tokens = await login(client, other_user.email, "other-password-12")

    create_response = await client.post(
        "/api/v1/keys",
        headers=auth_header(owner_tokens["access_token"]),
        json={"name": "owner-key", "scopes": ["jobs:read"]},
    )
    key_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/keys/{key_id}",
        headers=auth_header(other_tokens["access_token"]),
    )
    assert delete_response.status_code == 404


@pytest.mark.asyncio
async def test_create_key_rejects_unknown_scopes(client: AsyncClient, test_user):
    tokens = await login(client, test_user.email, "correct-password-12")
    response = await client.post(
        "/api/v1/keys",
        headers=auth_header(tokens["access_token"]),
        json={"name": "bad", "scopes": ["admin:destroy"]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_key_rejects_unknown_fields(client: AsyncClient, test_user):
    tokens = await login(client, test_user.email, "correct-password-12")
    response = await client.post(
        "/api/v1/keys",
        headers=auth_header(tokens["access_token"]),
        json={"name": "bad", "scopes": ["jobs:read"], "extra": "nope"},
    )
    assert response.status_code == 422
