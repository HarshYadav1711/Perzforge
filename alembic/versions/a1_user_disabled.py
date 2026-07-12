"""add users.disabled (story A1)

Revision ID: a1_user_disabled
Revises: a3_api_keys
Create Date: 2026-07-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1_user_disabled"
down_revision: str | None = "a3_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "disabled")
