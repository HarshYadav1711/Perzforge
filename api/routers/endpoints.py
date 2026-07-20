"""Inference endpoint routes (story C1)."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import api.serving as serving
from api.config import settings
from api.database import get_db
from api.deps import Principal, UserRole, require_scopes
from api.models import Endpoint, EndpointStatus, UsageLog
from api.schemas.endpoint import EndpointListResponse, EndpointResponse, PredictRequest

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


def _to_response(endpoint: Endpoint) -> EndpointResponse:
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


async def _get_owned_endpoint(
    db: AsyncSession,
    endpoint_id: uuid.UUID,
    principal: Principal,
) -> Endpoint:
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    endpoint = result.scalar_one_or_none()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    if endpoint.user_id != principal.user.id and principal.user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    return endpoint


@router.get("", response_model=EndpointListResponse)
async def list_endpoints(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_scopes("models:read")),
    db: AsyncSession = Depends(get_db),
):
    filters = [Endpoint.user_id == principal.user.id]
    total_result = await db.execute(select(func.count()).select_from(Endpoint).where(*filters))
    total = total_result.scalar_one()

    result = await db.execute(
        select(Endpoint)
        .where(*filters)
        .order_by(Endpoint.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [_to_response(ep) for ep in result.scalars().all()]
    return EndpointListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/{endpoint_id}/stop", response_model=EndpointResponse)
async def stop_endpoint(
    endpoint_id: uuid.UUID,
    principal: Principal = Depends(require_scopes("models:read")),
    db: AsyncSession = Depends(get_db),
):
    endpoint = await _get_owned_endpoint(db, endpoint_id, principal)
    if endpoint.status == EndpointStatus.STOPPED:
        return _to_response(endpoint)
    if endpoint.status not in (EndpointStatus.LIVE, EndpointStatus.STARTING, EndpointStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"endpoint cannot be stopped from status {endpoint.status.value}",
        )
    stopped = await serving.stop_endpoint_runtime(db, endpoint)
    return _to_response(stopped)


@router.post("/{route}/predict")
async def predict(
    route: str,
    body: PredictRequest,
    principal: Principal = Depends(require_scopes("llm:invoke")),
    db: AsyncSession = Depends(get_db),
):
    # Any authenticated caller with llm:invoke may invoke; ownership not required.
    result = await db.execute(select(Endpoint).where(Endpoint.route == route))
    endpoint = result.scalar_one_or_none()
    if endpoint is None or endpoint.status != EndpointStatus.LIVE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    if not endpoint.container_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    try:
        base_url = await asyncio.to_thread(serving.runner_base_url, endpoint.container_id)
    except serving.ServingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc

    predict_url = f"{base_url.rstrip('/')}/predict"
    timeout = httpx.Timeout(settings.serving_predict_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.post(predict_url, json=body.root)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="prediction timed out",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"prediction upstream error: {exc}",
        ) from exc

    api_key_id = principal.api_key.id if principal.api_key is not None else None
    db.add(
        UsageLog(
            user_id=principal.user.id,
            api_key_id=api_key_id,
            endpoint_id=endpoint.id,
            request_count=1,
        )
    )
    await db.commit()

    content_type = upstream.headers.get("content-type", "application/json")
    if "application/json" in content_type:
        try:
            payload: Any = upstream.json()
        except ValueError:
            return JSONResponse(
                status_code=upstream.status_code,
                content={"detail": "upstream returned invalid JSON"},
            )
        return JSONResponse(status_code=upstream.status_code, content=payload)

    return JSONResponse(
        status_code=upstream.status_code,
        content={"detail": upstream.text},
    )
