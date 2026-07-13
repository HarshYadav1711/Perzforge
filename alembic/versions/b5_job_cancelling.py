"""add CANCELLING job status (story B5)

Revision ID: b5_job_cancelling
Revises: b3_worker_execution
Create Date: 2026-07-14
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5_job_cancelling"
down_revision: str | None = "b3_worker_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "jobs",
        "status",
        existing_type=sa.String(length=9),
        type_=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "jobs",
        "status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=9),
        existing_nullable=False,
    )
