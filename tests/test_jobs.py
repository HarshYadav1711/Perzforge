"""Story B1 acceptance tests — job submission API."""
import pytest
from httpx import AsyncClient

from api.config import settings
from api.models import User
from api.queue import JOB_QUEUE_KEY
from tests.conftest import auth_header, login


def valid_job_payload(name: str = "train-cnn") -> dict:
    return {
        "name": name,
        "spec": {
            "image": "python:3.12-slim",
            "command": ["python", "train.py"],
            "env": {"EPOCHS": "10"},
            "gpu": False,
            "timeout_minutes": 60,
        },
    }


@pytest.mark.asyncio
async def test_submit_valid_job_is_queued_and_enqueued_in_redis(
    client: AsyncClient, test_user: User, fake_redis
):
    tokens = await login(client, test_user.email, "correct-password-12")
    response = await client.post(
        "/api/v1/jobs",
        headers=auth_header(tokens["access_token"]),
        json=valid_job_payload(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["name"] == "train-cnn"
    assert body["spec"]["command"] == ["python", "train.py"]

    queued_ids = await fake_redis.lrange(JOB_QUEUE_KEY, 0, -1)
    assert str(body["id"]) in queued_ids


@pytest.mark.asyncio
async def test_submit_rejects_shell_string_command(client: AsyncClient, test_user: User):
    tokens = await login(client, test_user.email, "correct-password-12")
    payload = valid_job_payload()
    payload["spec"]["command"] = "python train.py"

    response = await client.post(
        "/api/v1/jobs",
        headers=auth_header(tokens["access_token"]),
        json=payload,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rejects_unknown_spec_field(client: AsyncClient, test_user: User):
    tokens = await login(client, test_user.email, "correct-password-12")
    payload = valid_job_payload()
    payload["spec"]["dataset"] = "s3://bucket/data"

    response = await client.post(
        "/api/v1/jobs",
        headers=auth_header(tokens["access_token"]),
        json=payload,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rejects_disallowed_image(client: AsyncClient, test_user: User):
    tokens = await login(client, test_user.email, "correct-password-12")
    payload = valid_job_payload()
    payload["spec"]["image"] = "malicious/evil:latest"

    response = await client.post(
        "/api/v1/jobs",
        headers=auth_header(tokens["access_token"]),
        json=payload,
    )
    assert response.status_code == 422
    assert "image" in response.json()["detail"][0]["loc"]


@pytest.mark.asyncio
async def test_submit_over_concurrent_cap_returns_429(client: AsyncClient, test_user: User):
    tokens = await login(client, test_user.email, "correct-password-12")
    headers = auth_header(tokens["access_token"])

    for index in range(settings.max_concurrent_jobs_per_user):
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
    assert body["limit"] == settings.max_concurrent_jobs_per_user
    assert body["current"] == settings.max_concurrent_jobs_per_user
    assert "max_concurrent_jobs" in body["detail"]


@pytest.mark.asyncio
async def test_get_foreign_job_returns_404(
    client: AsyncClient, test_user: User, other_user: User, fake_redis
):
    owner_tokens = await login(client, test_user.email, "correct-password-12")
    create_response = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner_tokens["access_token"]),
        json=valid_job_payload(),
    )
    job_id = create_response.json()["id"]

    other_tokens = await login(client, other_user.email, "other-password-12")
    foreign_response = await client.get(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(other_tokens["access_token"]),
    )
    assert foreign_response.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs_returns_only_caller_jobs_newest_first(
    client: AsyncClient, test_user: User, other_user: User
):
    owner_tokens = await login(client, test_user.email, "correct-password-12")
    other_tokens = await login(client, other_user.email, "other-password-12")

    await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner_tokens["access_token"]),
        json=valid_job_payload(name="first-job"),
    )
    second = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner_tokens["access_token"]),
        json=valid_job_payload(name="second-job"),
    )
    await client.post(
        "/api/v1/jobs",
        headers=auth_header(other_tokens["access_token"]),
        json=valid_job_payload(name="other-job"),
    )

    list_response = await client.get(
        "/api/v1/jobs",
        headers=auth_header(owner_tokens["access_token"]),
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 2
    assert [item["name"] for item in body["items"]] == ["second-job", "first-job"]
    assert body["items"][0]["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_admin_can_get_foreign_job(
    client: AsyncClient, test_user: User, admin_user: User
):
    user_tokens = await login(client, test_user.email, "correct-password-12")
    create_response = await client.post(
        "/api/v1/jobs",
        headers=auth_header(user_tokens["access_token"]),
        json=valid_job_payload(),
    )
    job_id = create_response.json()["id"]

    admin_tokens = await login(client, admin_user.email, "admin-password-12")
    admin_response = await client.get(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(admin_tokens["access_token"]),
    )
    assert admin_response.status_code == 200


@pytest.mark.asyncio
async def test_api_key_with_jobs_write_can_submit_job(
    client: AsyncClient, test_user: User, fake_redis
):
    tokens = await login(client, test_user.email, "correct-password-12")
    from tests.conftest import create_api_key

    api_key = await create_api_key(
        client, tokens["access_token"], name="job-runner", scopes=["jobs:write"]
    )
    response = await client.post(
        "/api/v1/jobs",
        headers=auth_header(api_key),
        json=valid_job_payload(name="via-api-key"),
    )
    assert response.status_code == 201
