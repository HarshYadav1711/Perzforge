"""Model registry routes (story B4 / C1)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.deps import Principal, UserRole, require_scopes
from api.models import Endpoint, EndpointStatus, Model
from api.queue import get_redis
from api.quotas import QuotaResource, enforce, release
from api.schemas.endpoint import DeployRequest, EndpointResponse
from api.schemas.model import (
    ModelDownloadResponse,
    ModelListResponse,
    ModelResponse,
    PresignedFile,
)
import api.serving as serving
from api.storage import PRESIGN_EXPIRY_SECONDS, get_storage, size_to_storage_mb

router = APIRouter(prefix="/models", tags=["models"])


def _to_model_response(model: Model) -> ModelResponse:
    return ModelResponse(
        id=model.id,
        name=model.name,
        version=model.version,
        source_job_id=model.source_job_id,
        minio_prefix=model.minio_prefix,
        size_bytes=model.size_bytes,
        framework=model.framework,
        created_at=model.created_at,
    )


def _to_endpoint_response(endpoint: Endpoint) -> EndpointResponse:
    return EndpointResponse(
        id=endpoint.id,
        model_id=endpoint.model_id,
        name=endpoint.name,
        status=endpoint.status,
        route=endpoint.route,
        container_id=endpoint.container_id,
        error_message=endpoint.error_message,
        created_at=endpoint.created_at,
        stopped_at=endpoint.stopped_at,
    )


async def _get_owned_model(
    db: AsyncSession,
    model_id: uuid.UUID,
    principal: Principal,
) -> Model:
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    if model.user_id != principal.user.id and principal.user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    return model


@router.get("", response_model=ModelListResponse)
async def list_models(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_scopes("models:read")),
    db: AsyncSession = Depends(get_db),
):
    filters = [Model.user_id == principal.user.id]
    total_result = await db.execute(select(func.count()).select_from(Model).where(*filters))
    total = total_result.scalar_one()

    result = await db.execute(
        select(Model)
        .where(*filters)
        .order_by(Model.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [_to_model_response(model) for model in result.scalars().all()]
    return ModelListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: uuid.UUID,
    principal: Principal = Depends(require_scopes("models:read")),
    db: AsyncSession = Depends(get_db),
):
    model = await _get_owned_model(db, model_id, principal)
    return _to_model_response(model)


@router.get("/{model_id}/download", response_model=ModelDownloadResponse)
async def download_model(
    model_id: uuid.UUID,
    principal: Principal = Depends(require_scopes("models:read")),
    db: AsyncSession = Depends(get_db),
):
    model = await _get_owned_model(db, model_id, principal)
    storage = get_storage()
    files = storage.list_files(model.minio_prefix)
    return ModelDownloadResponse(
        files=[
            PresignedFile(
                key=str(item["key"]),
                url=storage.presign_get(str(item["full_key"])),
                size=int(item["size"]),
            )
            for item in files
        ],
        expires_in=PRESIGN_EXPIRY_SECONDS,
    )


@router.post(
    "/{model_id}/deploy",
    response_model=EndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def deploy_model(
    model_id: uuid.UUID,
    body: DeployRequest,
    principal: Principal = Depends(require_scopes("models:read")),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    model = await _get_owned_model(db, model_id, principal)
    await enforce(db, redis, principal.user, QuotaResource.LIVE_ENDPOINTS)

    endpoint_id = uuid.uuid4()
    display_name = body.name or model.name
    endpoint = Endpoint(
        id=endpoint_id,
        model_id=model.id,
        user_id=principal.user.id,
        name=display_name,
        status=EndpointStatus.STARTING,
        route=serving.make_route(display_name, endpoint_id),
    )
    db.add(endpoint)
    await db.commit()

    activated = await serving.activate_endpoint(db, endpoint, model)
    return _to_endpoint_response(activated)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_model(
    model_id: uuid.UUID,
    principal: Principal = Depends(require_scopes("models:read")),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    model = await _get_owned_model(db, model_id, principal)
    storage = get_storage()
    storage.delete_prefix(model.minio_prefix)

    storage_mb = size_to_storage_mb(model.size_bytes)
    if storage_mb > 0:
        await release(redis, principal.user, QuotaResource.STORAGE_MB, storage_mb)

    await db.execute(delete(Model).where(Model.id == model.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
