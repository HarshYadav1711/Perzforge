"""add models table and job mlflow/artifact columns (story B4)

Revision ID: b4_models_mlflow
Revises: e1_quotas
Create Date: 2026-07-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4_models_mlflow"
down_revision: str | None = "e1_quotas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("mlflow_run_id", sa.String(length=64), nullable=True))
    op.add_column("jobs", sa.Column("artifact_error", sa.String(length=1024), nullable=True))
    op.create_table(
        "models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("minio_prefix", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("framework", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", "version", name="uq_models_user_name_version"),
    )
    op.create_index(op.f("ix_models_user_id"), "models", ["user_id"], unique=False)
    op.create_index(op.f("ix_models_source_job_id"), "models", ["source_job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_models_source_job_id"), table_name="models")
    op.drop_index(op.f("ix_models_user_id"), table_name="models")
    op.drop_table("models")
    op.drop_column("jobs", "artifact_error")
    op.drop_column("jobs", "mlflow_run_id")
