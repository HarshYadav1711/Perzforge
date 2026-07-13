"""add quotas table (story E1)

Revision ID: e1_quotas
Revises: b5_job_cancelling
Create Date: 2026-07-14
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1_quotas"
down_revision: str | None = "b5_job_cancelling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quotas",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("max_concurrent_jobs", sa.Integer(), nullable=False),
        sa.Column("max_jobs_per_day", sa.Integer(), nullable=False),
        sa.Column("max_storage_mb", sa.Integer(), nullable=False),
        sa.Column("max_instances", sa.Integer(), nullable=False),
        sa.Column("max_llm_tokens_per_day", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("quotas")
