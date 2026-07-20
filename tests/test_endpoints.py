"""Story C1 acceptance tests — model deploy, predict, stop, reconcile."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from moto import mock_aws
from sqlalchemy import select

import api.database as database
from api.config import settings
from api.models import Endpoint, EndpointStatus, Model, UsageLog, User
from api.serving import reconcile_vanished_containers
from api.storage import ObjectStorage, model_prefix, reset_storage_cache
from tests.conftest import auth_header, create_api_key, login

TRIVIAL_SERVE_PY = '''\
def predict(payload: dict) -> dict:
    return {"echo": payload, "ok": True}
'''


@pytest.fixture
def minio_bucket(monkeypatch: pytest.MonkeyPatch):
    with mock_aws():
        monkeypatch.setattr(settings, "minio_endpoint", "https://s3.amazonaws.com")
        monkeypatch.setattr(settings, "minio_access_key", "testing")
        monkeypatch.setattr(settings, "minio_secret_key", "testing")
        monkeypatch.setattr(settings, "minio_bucket", "models")
        monkeypatch.setattr(settings, "minio_secure", True)
        reset_storage_cache()
        storage = ObjectStorage()
        storage.ensure_bucket()
        monkeypatch.setattr("api.storage.get_storage", lambda: storage)
        monkeypatch.setattr("api.routers.models.get_storage", lambda: storage)
        monkeypatch.setattr("api.serving.get_storage", lambda: storage)
        yield storage
        reset_storage_cache()


@pytest.fixture
def artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "endpoints"
    root.mkdir()
    monkeypatch.setattr(settings, "serving_artifact_root", str(root))
    return root


async def _seed_model(
    user: User,
    storage: ObjectStorage,
    *,
    name: str = "echo-model",
    with_serve: bool = True,
) -> Model:
    prefix = model_prefix(user.id, name, 1)
    if with_serve:
        storage.put_bytes(f"{prefix}serve.py", TRIVIAL_SERVE_PY.encode(), "text/x-python")
    storage.put_bytes(f"{prefix}weights.bin", b"fake-weights")
    async with database.SessionLocal() as session:
        model = Model(
            user_id=user.id,
            name=name,
            version=1,
            minio_prefix=prefix,
            size_bytes=100,
            framework="custom",
        )
        session.add(model)
        await session.commit()
        loaded = await session.get(Model, model.id)
        assert loaded is not None, "model seed did not persist"
        return loaded


def _patch_successful_runner(monkeypatch: pytest.MonkeyPatch, container_id: str = "ctr-c1") -> None:
    async def fake_activate(db, endpoint, model, storage=None):
        endpoint.status = EndpointStatus.LIVE
        endpoint.container_id = container_id
        endpoint.error_message = None
        endpoint.stopped_at = None
        await db.commit()
        return endpoint

    async def fake_stop(db, endpoint):
        endpoint.status = EndpointStatus.STOPPED
        endpoint.container_id = None
        endpoint.stopped_at = datetime.now(UTC)
        endpoint.error_message = None
        await db.commit()
        return endpoint

    monkeypatch.setattr("api.serving.activate_endpoint", fake_activate)
    monkeypatch.setattr("api.serving.stop_endpoint_runtime", fake_stop)
    monkeypatch.setattr("api.serving.runner_base_url", lambda cid: "http://127.0.0.1:19999")
    monkeypatch.setattr("api.serving.stop_runner_container", lambda cid: None)
    monkeypatch.setattr("api.serving.container_exists", lambda cid: cid == container_id)
    monkeypatch.setattr("api.serving.cleanup_artifact_dir", lambda eid: None)


@pytest.mark.asyncio
async def test_deploy_predict_stop_cycle(
    client: AsyncClient,
    test_user: User,
    other_user: User,
    minio_bucket: ObjectStorage,
    artifact_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_successful_runner(monkeypatch)
    model = await _seed_model(test_user, minio_bucket)

    # Mock httpx proxy used by predict
    mock_response = httpx.Response(200, json={"echo": {"x": 1}, "ok": True})

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None):
            assert url.endswith("/predict")
            assert json == {"x": 1}
            return mock_response

    monkeypatch.setattr("api.routers.endpoints.httpx.AsyncClient", FakeAsyncClient)

    owner_tokens = await login(client, test_user.email, "correct-password-12")
    owner_headers = auth_header(owner_tokens["access_token"])

    deploy = await client.post(
        f"/api/v1/models/{model.id}/deploy",
        headers=owner_headers,
        json={},
    )
    assert deploy.status_code == 201, deploy.text
    endpoint = deploy.json()
    assert endpoint["status"] == "LIVE"
    assert endpoint["route"]
    assert endpoint["model_id"] == str(model.id)
    route = endpoint["route"]
    endpoint_id = endpoint["id"]

    # Owner predict
    predict = await client.post(
        f"/api/v1/endpoints/{route}/predict",
        headers=owner_headers,
        json={"x": 1},
    )
    assert predict.status_code == 200, predict.text
    assert predict.json()["ok"] is True

    # Non-owner can predict (caller-shareable)
    other_tokens = await login(client, other_user.email, "other-password-12")
    other_predict = await client.post(
        f"/api/v1/endpoints/{route}/predict",
        headers=auth_header(other_tokens["access_token"]),
        json={"x": 1},
    )
    assert other_predict.status_code == 200, other_predict.text

    async with database.SessionLocal() as session:
        logs = (await session.execute(select(UsageLog))).scalars().all()
        assert len(logs) == 2
        callers = {log.user_id for log in logs}
        assert callers == {test_user.id, other_user.id}

    # Non-owner cannot stop → 404
    other_stop = await client.post(
        f"/api/v1/endpoints/{endpoint_id}/stop",
        headers=auth_header(other_tokens["access_token"]),
    )
    assert other_stop.status_code == 404

    # Owner stop
    stop = await client.post(
        f"/api/v1/endpoints/{endpoint_id}/stop",
        headers=owner_headers,
    )
    assert stop.status_code == 200, stop.text
    assert stop.json()["status"] == "STOPPED"
    assert stop.json()["stopped_at"] is not None

    # Predict after stop → 404
    after = await client.post(
        f"/api/v1/endpoints/{route}/predict",
        headers=owner_headers,
        json={"x": 1},
    )
    assert after.status_code == 404


@pytest.mark.asyncio
async def test_contract_violation_missing_serve_py(
    client: AsyncClient,
    test_user: User,
    minio_bucket: ObjectStorage,
    artifact_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    started = {"called": False}

    def _should_not_start(*_args, **_kwargs):
        started["called"] = True
        raise AssertionError("runner must not start without serve.py")

    monkeypatch.setattr("api.serving.start_runner_container", _should_not_start)

    model = await _seed_model(test_user, minio_bucket, name="broken", with_serve=False)
    tokens = await login(client, test_user.email, "correct-password-12")

    deploy = await client.post(
        f"/api/v1/models/{model.id}/deploy",
        headers=auth_header(tokens["access_token"]),
        json={},
    )
    assert deploy.status_code == 201, deploy.text
    body = deploy.json()
    assert body["status"] == "FAILED"
    assert body["error_message"] is not None
    assert "serve.py" in body["error_message"]
    assert started["called"] is False


@pytest.mark.asyncio
async def test_non_owner_can_predict_with_api_key_but_cannot_stop(
    client: AsyncClient,
    test_user: User,
    other_user: User,
    minio_bucket: ObjectStorage,
    artifact_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_successful_runner(monkeypatch)

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None):
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("api.routers.endpoints.httpx.AsyncClient", FakeAsyncClient)

    model = await _seed_model(test_user, minio_bucket)
    owner_tokens = await login(client, test_user.email, "correct-password-12")
    deploy = await client.post(
        f"/api/v1/models/{model.id}/deploy",
        headers=auth_header(owner_tokens["access_token"]),
        json={},
    )
    assert deploy.status_code == 201
    route = deploy.json()["route"]
    endpoint_id = deploy.json()["id"]

    other_tokens = await login(client, other_user.email, "other-password-12")
    api_key = await create_api_key(
        client,
        other_tokens["access_token"],
        name="infer",
        scopes=["llm:invoke"],
    )

    predict = await client.post(
        f"/api/v1/endpoints/{route}/predict",
        headers=auth_header(api_key),
        json={"q": "hi"},
    )
    assert predict.status_code == 200, predict.text

    stop = await client.post(
        f"/api/v1/endpoints/{endpoint_id}/stop",
        headers=auth_header(api_key),
    )
    # API key lacks models:read → 403 scope; JWT non-owner with models:read → 404.
    # Task: non-owner cannot stop (404). Use JWT for ownership check.
    stop_jwt = await client.post(
        f"/api/v1/endpoints/{endpoint_id}/stop",
        headers=auth_header(other_tokens["access_token"]),
    )
    assert stop_jwt.status_code == 404
    assert stop.status_code in (403, 404)


@pytest.mark.asyncio
async def test_startup_reconciliation_marks_vanished_container_failed(
    test_user: User,
    minio_bucket: ObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
):
    model = await _seed_model(test_user, minio_bucket)
    endpoint_id = uuid.uuid4()
    async with database.SessionLocal() as session:
        endpoint = Endpoint(
            id=endpoint_id,
            model_id=model.id,
            user_id=test_user.id,
            name="orphan",
            status=EndpointStatus.LIVE,
            container_id="vanished-ctr",
            route=f"orphan-{endpoint_id.hex[:8]}",
            created_at=datetime.now(UTC),
        )
        session.add(endpoint)
        await session.commit()

    monkeypatch.setattr("api.serving.container_exists", lambda cid: False)
    monkeypatch.setattr("api.serving.stop_runner_container", lambda cid: None)
    monkeypatch.setattr("api.serving.cleanup_artifact_dir", lambda eid: None)

    async with database.SessionLocal() as session:
        marked = await reconcile_vanished_containers(session)
        assert marked == 1
        refreshed = await session.get(Endpoint, endpoint_id)
        assert refreshed is not None
        assert refreshed.status == EndpointStatus.FAILED
        assert refreshed.container_id is None
        assert "vanished" in (refreshed.error_message or "").lower()


@pytest.mark.asyncio
async def test_live_endpoint_quota_blocks_second_deploy(
    client: AsyncClient,
    test_user: User,
    minio_bucket: ObjectStorage,
    artifact_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_successful_runner(monkeypatch, container_id="ctr-1")
    model_a = await _seed_model(test_user, minio_bucket, name="a")
    model_b = await _seed_model(test_user, minio_bucket, name="b")

    tokens = await login(client, test_user.email, "correct-password-12")
    headers = auth_header(tokens["access_token"])

    first = await client.post(f"/api/v1/models/{model_a.id}/deploy", headers=headers, json={})
    assert first.status_code == 201
    assert first.json()["status"] == "LIVE"

    second = await client.post(f"/api/v1/models/{model_b.id}/deploy", headers=headers, json={})
    assert second.status_code == 429
    assert second.json()["quota"] == "max_live_endpoints"


@pytest.mark.asyncio
async def test_list_endpoints_owner_only(
    client: AsyncClient,
    test_user: User,
    other_user: User,
    minio_bucket: ObjectStorage,
    artifact_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_successful_runner(monkeypatch)
    model = await _seed_model(test_user, minio_bucket)
    owner_tokens = await login(client, test_user.email, "correct-password-12")
    deploy = await client.post(
        f"/api/v1/models/{model.id}/deploy",
        headers=auth_header(owner_tokens["access_token"]),
        json={},
    )
    assert deploy.status_code == 201

    owner_list = await client.get(
        "/api/v1/endpoints",
        headers=auth_header(owner_tokens["access_token"]),
    )
    assert owner_list.status_code == 200
    assert owner_list.json()["total"] == 1

    other_tokens = await login(client, other_user.email, "other-password-12")
    other_list = await client.get(
        "/api/v1/endpoints",
        headers=auth_header(other_tokens["access_token"]),
    )
    assert other_list.status_code == 200
    assert other_list.json()["total"] == 0
