"""Artifact promotion from job outputs to MinIO model registry (story B4)."""
from __future__ import annotations

import uuid
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy import func, select

import api.database as database
from api.models import Model, User
from api.quotas import QuotaExceededError, QuotaResource, enforce
from api.storage import ObjectStorage, model_prefix, size_to_storage_mb


def _dir_size_bytes(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def _iter_files(directory: Path) -> list[Path]:
    return [path for path in directory.rglob("*") if path.is_file()]


async def next_model_version(user_id: uuid.UUID, name: str) -> int:
    async with database.SessionLocal() as session:
        result = await session.execute(
            select(func.coalesce(func.max(Model.version), 0)).where(
                Model.user_id == user_id,
                Model.name == name,
            )
        )
        return int(result.scalar_one()) + 1


async def promote_outputs(
    *,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    job_name: str,
    outputs_dir: Path | None,
    redis: Redis,
    storage: ObjectStorage,
    framework: str | None = None,
) -> tuple[Model | None, str | None]:
    """Upload /workspace/outputs to MinIO and create a Model row.

    Returns (model, artifact_error). Empty outputs → (None, None).
    Over-quota → (None, error message); caller keeps job SUCCEEDED.
    """
    if outputs_dir is None or not outputs_dir.is_dir():
        return None, None

    files = _iter_files(outputs_dir)
    if not files:
        return None, None

    size_bytes = _dir_size_bytes(outputs_dir)
    storage_mb = size_to_storage_mb(size_bytes)

    async with database.SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            return None, "user not found for artifact upload"
        try:
            await enforce(session, redis, user, QuotaResource.STORAGE_MB, storage_mb)
        except QuotaExceededError as exc:
            return None, exc.detail

    version = await next_model_version(user_id, job_name)
    prefix = model_prefix(user_id, job_name, version)

    for path in files:
        relative = path.relative_to(outputs_dir).as_posix()
        key = f"{prefix}{relative}"
        storage.put_bytes(key, path.read_bytes())

    async with database.SessionLocal() as session:
        model = Model(
            user_id=user_id,
            name=job_name,
            version=version,
            source_job_id=job_id,
            minio_prefix=prefix,
            size_bytes=size_bytes,
            framework=framework,
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return model, None
