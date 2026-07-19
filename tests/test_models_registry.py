"""Story B4 acceptance tests — model registry, MinIO artifacts, quotas."""
import math
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient
from moto import mock_aws
from sqlalchemy import select

import api.database as database
from api.config import settings
from api.models import Job, JobStatus, Model, Quota, User
from api.quotas import QuotaResource, quota_counter_key
from api.storage import ObjectStorage, model_prefix, reset_storage_cache, user_prefix
from tests.conftest import auth_header, login
from worker.artifacts import promote_outputs


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
        monkeypatch.setattr("worker.agent.get_storage", lambda: storage)
        yield storage
        reset_storage_cache()


def _write_outputs(tmp_path: Path, files: dict[str, bytes]) -> Path:
    out = tmp_path / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return out


async def _seed_job(user: User, name: str = "train-cnn") -> Job:
    async with database.SessionLocal() as session:
        job = Job(
            user_id=user.id,
            name=name,
            spec={
                "image": "python:3.12-slim",
                "command": ["python", "-c", "print(1)"],
                "env": {},
                "gpu": False,
                "timeout_minutes": 60,
            },
            status=JobStatus.RUNNING,
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            worker_id="test-worker",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


@pytest.mark.asyncio
async def test_promote_outputs_uploads_and_versions(
    test_user: User,
    fake_redis,
    minio_bucket: ObjectStorage,
    tmp_path: Path,
):
    job = await _seed_job(test_user, name="resnet")
    outputs = _write_outputs(tmp_path, {"model.pt": b"weights-v1"})

    model, error = await promote_outputs(
        job_id=job.id,
        user_id=test_user.id,
        job_name=job.name,
        outputs_dir=outputs,
        redis=fake_redis,
        storage=minio_bucket,
    )
    assert error is None
    assert model is not None
    assert model.version == 1
    assert model.name == "resnet"
    assert model.minio_prefix == model_prefix(test_user.id, "resnet", 1)
    assert minio_bucket.object_exists(f"{model.minio_prefix}model.pt")

    outputs2 = _write_outputs(tmp_path / "v2", {"model.pt": b"weights-v2"})
    model2, error2 = await promote_outputs(
        job_id=job.id,
        user_id=test_user.id,
        job_name=job.name,
        outputs_dir=outputs2,
        redis=fake_redis,
        storage=minio_bucket,
    )
    assert error2 is None
    assert model2 is not None
    assert model2.version == 2


@pytest.mark.asyncio
async def test_empty_outputs_is_noop(
    test_user: User,
    fake_redis,
    minio_bucket: ObjectStorage,
    tmp_path: Path,
):
    job = await _seed_job(test_user)
    empty = tmp_path / "outputs"
    empty.mkdir()

    model, error = await promote_outputs(
        job_id=job.id,
        user_id=test_user.id,
        job_name=job.name,
        outputs_dir=empty,
        redis=fake_redis,
        storage=minio_bucket,
    )
    assert model is None
    assert error is None

    async with database.SessionLocal() as session:
        result = await session.execute(select(Model))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_quota_exceeded_skips_model_and_surfaces_error(
    test_user: User,
    fake_redis,
    minio_bucket: ObjectStorage,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "max_storage_mb_per_user", 1)
    async with database.SessionLocal() as session:
        session.add(
            Quota(
                user_id=test_user.id,
                max_concurrent_jobs=2,
                max_jobs_per_day=10,
                max_storage_mb=1,
                max_instances=1,
                max_llm_tokens_per_day=50000,
            )
        )
        await session.commit()

    # Already at limit
    await fake_redis.set(quota_counter_key(test_user.id, QuotaResource.STORAGE_MB), "1")

    job = await _seed_job(test_user)
    outputs = _write_outputs(tmp_path, {"big.bin": b"x" * 100})

    model, error = await promote_outputs(
        job_id=job.id,
        user_id=test_user.id,
        job_name=job.name,
        outputs_dir=outputs,
        redis=fake_redis,
        storage=minio_bucket,
    )
    assert model is None
    assert error is not None
    assert "max_storage_mb" in error

    async with database.SessionLocal() as session:
        result = await session.execute(select(Model))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_list_and_get_models_own_only(
    client: AsyncClient,
    test_user: User,
    other_user: User,
    minio_bucket: ObjectStorage,
):
    prefix_a = model_prefix(test_user.id, "alpha", 1)
    minio_bucket.put_bytes(f"{prefix_a}weights.bin", b"aaa")
    prefix_b = model_prefix(other_user.id, "beta", 1)
    minio_bucket.put_bytes(f"{prefix_b}weights.bin", b"bbb")

    async with database.SessionLocal() as session:
        session.add(
            Model(
                user_id=test_user.id,
                name="alpha",
                version=1,
                source_job_id=None,
                minio_prefix=prefix_a,
                size_bytes=3,
                framework=None,
            )
        )
        session.add(
            Model(
                user_id=other_user.id,
                name="beta",
                version=1,
                source_job_id=None,
                minio_prefix=prefix_b,
                size_bytes=3,
                framework=None,
            )
        )
        await session.commit()

    tokens = await login(client, test_user.email, "correct-password-12")
    headers = auth_header(tokens["access_token"])

    listed = await client.get("/api/v1/models", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "alpha"
    model_id = body["items"][0]["id"]

    got = await client.get(f"/api/v1/models/{model_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["version"] == 1

    other_tokens = await login(client, other_user.email, "other-password-12")
    other_headers = auth_header(other_tokens["access_token"])
    forbidden = await client.get(f"/api/v1/models/{model_id}", headers=other_headers)
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_presign_isolation_returns_404_for_other_users_model(
    client: AsyncClient,
    test_user: User,
    other_user: User,
    minio_bucket: ObjectStorage,
):
    prefix = model_prefix(test_user.id, "secret", 1)
    minio_bucket.put_bytes(f"{prefix}a.bin", b"data")
    async with database.SessionLocal() as session:
        model = Model(
            user_id=test_user.id,
            name="secret",
            version=1,
            source_job_id=None,
            minio_prefix=prefix,
            size_bytes=4,
            framework=None,
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        model_id = model.id

    other_tokens = await login(client, other_user.email, "other-password-12")
    response = await client.get(
        f"/api/v1/models/{model_id}/download",
        headers=auth_header(other_tokens["access_token"]),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_returns_presigned_urls(
    client: AsyncClient,
    test_user: User,
    minio_bucket: ObjectStorage,
):
    prefix = model_prefix(test_user.id, "pack", 1)
    minio_bucket.put_bytes(f"{prefix}a.bin", b"aaa")
    minio_bucket.put_bytes(f"{prefix}b.bin", b"bbbb")
    async with database.SessionLocal() as session:
        model = Model(
            user_id=test_user.id,
            name="pack",
            version=1,
            source_job_id=None,
            minio_prefix=prefix,
            size_bytes=7,
            framework="pytorch",
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        model_id = model.id

    tokens = await login(client, test_user.email, "correct-password-12")
    response = await client.get(
        f"/api/v1/models/{model_id}/download",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 900
    assert len(body["files"]) == 2
    keys = {f["key"] for f in body["files"]}
    assert keys == {"a.bin", "b.bin"}
    assert all(f["url"].startswith("https://") for f in body["files"])


@pytest.mark.asyncio
async def test_delete_model_removes_objects_and_releases_quota(
    client: AsyncClient,
    test_user: User,
    fake_redis,
    minio_bucket: ObjectStorage,
):
    prefix = model_prefix(test_user.id, "todelete", 1)
    minio_bucket.put_bytes(f"{prefix}x.bin", b"12345")
    size_mb = max(1, math.ceil(5 / (1024 * 1024)))
    await fake_redis.set(
        quota_counter_key(test_user.id, QuotaResource.STORAGE_MB),
        str(size_mb),
    )

    async with database.SessionLocal() as session:
        model = Model(
            user_id=test_user.id,
            name="todelete",
            version=1,
            source_job_id=None,
            minio_prefix=prefix,
            size_bytes=5,
            framework=None,
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        model_id = model.id

    tokens = await login(client, test_user.email, "correct-password-12")
    response = await client.delete(
        f"/api/v1/models/{model_id}",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 204
    assert not minio_bucket.object_exists(f"{prefix}x.bin")

    usage = await fake_redis.get(quota_counter_key(test_user.id, QuotaResource.STORAGE_MB))
    assert int(usage or "0") == 0

    async with database.SessionLocal() as session:
        assert await session.get(Model, model_id) is None


@pytest.mark.asyncio
async def test_user_prefix_isolation_convention():
    uid = uuid.uuid4()
    assert user_prefix(uid) == f"users/{uid}/"
    assert model_prefix(uid, "n", 3) == f"models/{uid}/n/3/"


@pytest.mark.asyncio
async def test_job_response_includes_artifact_error_and_mlflow_run_id(
    client: AsyncClient,
    test_user: User,
):
    async with database.SessionLocal() as session:
        job = Job(
            user_id=test_user.id,
            name="tracked",
            spec={
                "image": "python:3.12-slim",
                "command": ["python", "-c", "print(1)"],
                "env": {},
                "gpu": False,
                "timeout_minutes": 60,
            },
            status=JobStatus.SUCCEEDED,
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            exit_code=0,
            mlflow_run_id="abc123",
            artifact_error="max_storage_mb quota exceeded (1/1)",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    tokens = await login(client, test_user.email, "correct-password-12")
    response = await client.get(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mlflow_run_id"] == "abc123"
    assert "max_storage_mb" in body["artifact_error"]


@pytest.mark.asyncio
async def test_process_job_promotes_outputs_on_success(
    fake_redis,
    test_user: User,
    minio_bucket: ObjectStorage,
    tmp_path: Path,
):
    job = await _seed_job(test_user, name="promote-me")
    outputs = _write_outputs(tmp_path, {"model.bin": b"payload"})

    model, error = await promote_outputs(
        job_id=job.id,
        user_id=test_user.id,
        job_name=job.name,
        outputs_dir=outputs,
        redis=fake_redis,
        storage=minio_bucket,
    )
    assert error is None
    assert model is not None
    assert model.version == 1
    assert model.source_job_id == job.id

    async with database.SessionLocal() as session:
        rows = (
            await session.execute(select(Model).where(Model.source_job_id == job.id))
        ).scalars().all()
        assert len(rows) == 1
