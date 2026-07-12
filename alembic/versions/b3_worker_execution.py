"""worker execution + job logs (story B3)

Revision ID: b3_worker_execution
Revises: b1_jobs
Create Date: 2026-07-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3_worker_execution"
down_revision: str | None = "b1_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "jobs",
        "worker_id",
        existing_type=postgresql.UUID(),
        type_=sa.String(length=128),
        existing_nullable=True,
        postgresql_using="worker_id::text",
    )

    op.create_table(
        "job_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_job_logs_job_id"), "job_logs", ["job_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_job_logs_job_id"), table_name="job_logs")
    op.drop_table("job_logs")
    op.alter_column(
        "jobs",
        "worker_id",
        existing_type=sa.String(length=128),
        type_=postgresql.UUID(),
        existing_nullable=True,
        postgresql_using="NULL::uuid",
    )
