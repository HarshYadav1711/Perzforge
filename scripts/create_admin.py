#!/usr/bin/env python3
"""Create the first admin user from environment variables.

Usage:
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='...' python scripts/create_admin.py

Only creates a user when no admin exists yet.
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from api.database import SessionLocal
from api.models import User, UserRole
from api.security import hash_password


async def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")

    if not email or not password:
        print("ADMIN_EMAIL and ADMIN_PASSWORD environment variables are required.", file=sys.stderr)
        return 1

    async with SessionLocal() as db:
        existing_admin = await db.execute(select(User).where(User.role == UserRole.admin))
        if existing_admin.scalar_one_or_none() is not None:
            print("An admin user already exists; refusing to create another.")
            return 0

        email_taken = await db.execute(select(User).where(User.email == email))
        if email_taken.scalar_one_or_none() is not None:
            print(f"User with email {email} already exists.", file=sys.stderr)
            return 1

        user = User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.admin,
            must_change_password=False,
        )
        db.add(user)
        await db.commit()
        print(f"Created admin user: {email}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
