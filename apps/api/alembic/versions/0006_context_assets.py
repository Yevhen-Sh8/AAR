"""context_assets table + asset_usages

Revision ID: 0006_context_assets
Revises: 0005_audit_log
Create Date: 2026-05-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_context_assets"
down_revision: Union[str, None] = "0005_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "context_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_agent", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("reusable_for", sa.JSON(), nullable=False),
        sa.Column("owner_role", sa.String(32), nullable=False, server_default="manager"),
        sa.Column(
            "validated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "superseded_by_id",
            sa.Integer(),
            sa.ForeignKey("context_assets.id"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.String(512), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_context_assets_type", "context_assets", ["type"])
    op.create_index("ix_context_assets_status", "context_assets", ["status"])

    op.create_table(
        "context_asset_usages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "asset_id", sa.Integer(), sa.ForeignKey("context_assets.id"), nullable=False
        ),
        sa.Column("used_in", sa.String(64), nullable=False),
        sa.Column("used_by_agent", sa.String(64), nullable=True),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_context_asset_usages_asset_id", "context_asset_usages", ["asset_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_context_asset_usages_asset_id", table_name="context_asset_usages")
    op.drop_table("context_asset_usages")
    op.drop_index("ix_context_assets_status", table_name="context_assets")
    op.drop_index("ix_context_assets_type", table_name="context_assets")
    op.drop_table("context_assets")
