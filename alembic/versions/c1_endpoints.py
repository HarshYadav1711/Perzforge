"""endpoints, usage_logs, max_live_endpoints (story C1)

Revision ID: c1_endpoints
Revises: b4_models_mlflow
Create Date: 2026-07-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1_endpoints"
down_revision: str | None = "b4_models_mlflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quotas",
        sa.Column("max_live_endpoints", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("quotas", "max_live_endpoints", server_default=None)

    op.create_table(
        "endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("container_id", sa.String(length=128), nullable=True),
        sa.Column("route", sa.String(length=160), nullable=False),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route"),
    )
    op.create_index(op.f("ix_endpoints_model_id"), "endpoints", ["model_id"], unique=False)
    op.create_index(op.f("ix_endpoints_user_id"), "endpoints", ["user_id"], unique=False)
    op.create_index(op.f("ix_endpoints_route"), "endpoints", ["route"], unique=False)

    op.create_table(
        "usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usage_logs_user_id"), "usage_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_usage_logs_api_key_id"), "usage_logs", ["api_key_id"], unique=False)
    op.create_index(op.f("ix_usage_logs_endpoint_id"), "usage_logs", ["endpoint_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_logs_endpoint_id"), table_name="usage_logs")
    op.drop_index(op.f("ix_usage_logs_api_key_id"), table_name="usage_logs")
    op.drop_index(op.f("ix_usage_logs_user_id"), table_name="usage_logs")
    op.drop_table("usage_logs")
    op.drop_index(op.f("ix_endpoints_route"), table_name="endpoints")
    op.drop_index(op.f("ix_endpoints_user_id"), table_name="endpoints")
    op.drop_index(op.f("ix_endpoints_model_id"), table_name="endpoints")
    op.drop_table("endpoints")
    op.drop_column("quotas", "max_live_endpoints")
