"""Authentication routes (story A2)."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.deps import get_current_user
from api.models import RefreshToken, User
from api.security import (
    create_access_token,
    generate_refresh_token,
    hash_token,
    refresh_token_expires_at,
    verify_password_constant_time,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
INVALID_CREDENTIALS = "Invalid email or password"
INVALID_REFRESH = "Invalid or expired refresh token"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    must_change_password: bool


def _refresh_cookie_kwargs() -> dict:
    return {
        "key": REFRESH_COOKIE,
        "httponly": True,
        "secure": settings.environment != "dev",
        "samesite": "strict",
        "path": "/api/v1/auth",
    }


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        value=token,
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        **_refresh_cookie_kwargs(),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(**_refresh_cookie_kwargs())


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def _get_refresh_token_row(db: AsyncSession, token: str) -> RefreshToken | None:
    token_hash = hash_token(token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    return result.scalar_one_or_none()


async def _revoke_token_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id)
        .values(revoked=True)
    )


async def _issue_refresh_token(
    db: AsyncSession,
    user: User,
    family_id: uuid.UUID | None = None,
) -> str:
    plain_token = generate_refresh_token()
    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(plain_token),
        family_id=family_id or uuid.uuid4(),
        expires_at=refresh_token_expires_at(),
        revoked=False,
    )
    db.add(row)
    await db.flush()
    return plain_token


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role.value,
        must_change_password=user.must_change_password,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # public: credential exchange endpoint
    user = await _get_user_by_email(db, body.email.lower())
    if not verify_password_constant_time(body.password, user.password_hash if user else None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
        )

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = await _issue_refresh_token(db, user)
    await db.commit()

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # public: credential exchange endpoint
    plain_token = request.cookies.get(REFRESH_COOKIE)
    if not plain_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_REFRESH,
        )

    row = await _get_refresh_token_row(db, plain_token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_REFRESH,
        )

    if row.revoked:
        await _revoke_token_family(db, row.family_id)
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_REFRESH,
        )

    now = datetime.now(UTC)
    if row.expires_at <= now:
        row.revoked = True
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_REFRESH,
        )

    user = await db.get(User, row.user_id)
    if user is None:
        await _revoke_token_family(db, row.family_id)
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_REFRESH,
        )

    row.revoked = True
    new_refresh_token = await _issue_refresh_token(db, user, family_id=row.family_id)
    access_token = create_access_token(user.id, user.role.value)
    await db.commit()

    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # public: revokes session using httpOnly refresh cookie only
    plain_token = request.cookies.get(REFRESH_COOKIE)
    if plain_token:
        row = await _get_refresh_token_row(db, plain_token)
        if row is not None:
            await _revoke_token_family(db, row.family_id)
            await db.commit()

    _clear_refresh_cookie(response)
