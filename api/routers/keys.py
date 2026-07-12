"""API key management routes (story A3)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.deps import get_current_user
from api.models import ApiKey, User
from api.scopes import VALID_SCOPES, scopes_allowed_for_role
from api.security import generate_api_key

router = APIRouter(prefix="/keys", tags=["keys"])


class CreateApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: list[str]) -> list[str]:
        unknown = [scope for scope in scopes if scope not in VALID_SCOPES]
        if unknown:
            raise ValueError(f"Unknown scopes: {', '.join(unknown)}")
        if len(scopes) != len(set(scopes)):
            raise ValueError("Duplicate scopes are not allowed")
        return scopes


class ApiKeyCreatedResponse(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    rate_limit_tier: str
    expires_at: datetime | None
    revoked: bool
    last_used_at: datetime | None
    created_at: datetime
    store_this_now: str


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    rate_limit_tier: str
    expires_at: datetime | None
    revoked: bool
    last_used_at: datetime | None
    created_at: datetime


def _to_response(api_key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        scopes=api_key.scopes,
        rate_limit_tier=api_key.rate_limit_tier,
        expires_at=api_key.expires_at,
        revoked=api_key.revoked,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
    )


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not scopes_allowed_for_role(user.role, body.scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested scopes exceed your role",
        )

    plaintext, key_hash, prefix = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        name=body.name,
        key_hash=key_hash,
        prefix=prefix,
        scopes=body.scopes,
        expires_at=body.expires_at,
        revoked=False,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    response = _to_response(api_key)
    return ApiKeyCreatedResponse(
        **response.model_dump(),
        store_this_now=plaintext,
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return [_to_response(row) for row in result.scalars().all()]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    api_key.revoked = True
    await db.commit()
