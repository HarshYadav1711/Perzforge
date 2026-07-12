"""Admin user management routes (story A1)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.deps import get_current_admin
from api.models import User, UserRole
from api.security import generate_temporary_password, hash_password

router = APIRouter(prefix="/admin/users", tags=["admin"])


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: UserRole = UserRole.user


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    must_change_password: bool
    disabled: bool
    created_at: datetime


class AdminUserCreatedResponse(AdminUserResponse):
    temporary_password: str


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
    limit: int
    offset: int


def _to_admin_user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        role=user.role.value,
        must_change_password=user.must_change_password,
        disabled=user.disabled,
        created_at=user.created_at,
    )


@router.post("", response_model=AdminUserCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    email = body.email.lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    temporary_password = generate_temporary_password()
    user = User(
        email=email,
        password_hash=hash_password(temporary_password),
        role=body.role,
        must_change_password=True,
        disabled=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    response = _to_admin_user_response(user)
    return AdminUserCreatedResponse(
        **response.model_dump(),
        temporary_password=temporary_password,
    )


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one()

    result = await db.execute(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    items = [_to_admin_user_response(user) for user in result.scalars().all()]
    return AdminUserListResponse(items=items, total=total, limit=limit, offset=offset)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_user(
    user_id: uuid.UUID,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == _admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admins cannot disable their own account",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.disabled = True
    await db.commit()
