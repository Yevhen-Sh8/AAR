"""integrations: location on events, subscriptions, deliveries

Revision ID: 0004_integrations
Revises: 0003_offline_idempotency
Create Date: 2026-05-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_integrations"
down_revision: Union[str, None] = "0003_offline_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usage_events", sa.Column("location", sa.JSON(), nullable=True))

    op.create_table(
        "integration_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("target_url", sa.String(512), nullable=False),
        sa.Column("secret", sa.String(256), nullable=True),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "integration_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(1024), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "dispatched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_deliveries_subscription_id",
        "integration_deliveries",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_deliveries_subscription_id", table_name="integration_deliveries")
    op.drop_table("integration_deliveries")
    op.drop_table("integration_subscriptions")
    op.drop_column("usage_events", "location")
