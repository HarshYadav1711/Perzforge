"""Shared dependencies."""
import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import SessionLocal, get_db
from api.models import ApiKey, User, UserRole
from api.scopes import ROLE_SCOPES
from api.security import decode_access_token, hash_token, is_api_key_token

bearer = HTTPBearer(auto_error=False)
PASSWORD_CHANGE_REQUIRED = "password change required"
ACCOUNT_DISABLED = "Account disabled"


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    api_key: ApiKey | None = None

    @property
    def scopes(self) -> frozenset[str]:
        if self.api_key is not None:
            return frozenset(self.api_key.scopes)
        return ROLE_SCOPES[self.user.role]


def _reject_disabled_user(user: User) -> None:
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ACCOUNT_DISABLED,
        )


def _reject_password_change_required(user: User) -> None:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PASSWORD_CHANGE_REQUIRED,
        )


async def _touch_api_key_last_used(key_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(ApiKey)
            .where(ApiKey.id == key_id)
            .values(last_used_at=datetime.now(UTC))
        )
        await session.commit()


async def _authenticate_api_key(token: str, db: AsyncSession) -> Principal:
    token_hash = hash_token(token)
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == token_hash))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    if api_key.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    now = datetime.now(UTC)
    if api_key.expires_at is not None and api_key.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    user = await db.get(User, api_key.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    _reject_disabled_user(user)

    asyncio.create_task(_touch_api_key_last_used(api_key.id))
    return Principal(user=user, api_key=api_key)


async def _authenticate_jwt(token: str, db: AsyncSession) -> Principal:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    _reject_disabled_user(user)
    return Principal(user=user)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return await resolve_principal_from_token(credentials.credentials, db)


async def resolve_principal_from_token(token: str, db: AsyncSession) -> Principal:
    if is_api_key_token(token):
        principal = await _authenticate_api_key(token, db)
    else:
        principal = await _authenticate_jwt(token, db)

    _reject_password_change_required(principal.user)
    return principal


async def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = credentials.credentials
    if is_api_key_token(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="JWT required for this endpoint",
        )

    principal = await _authenticate_jwt(token, db)
    return principal.user


async def get_current_user(user: User = Depends(get_authenticated_user)) -> User:
    _reject_password_change_required(user)
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


def require_scopes(*required_scopes: str) -> Callable:
    async def _require_scopes(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        missing = [scope for scope in required_scopes if scope not in principal.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient scope",
            )
        return principal

    return _require_scopes
