"""add client_event_id to usage_events for offline idempotency

Revision ID: 0003_offline_idempotency
Revises: 0002_data_model
Create Date: 2026-05-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_offline_idempotency"
down_revision: Union[str, None] = "0002_data_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usage_events", sa.Column("client_event_id", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_usage_events_client_event_id",
        "usage_events",
        ["client_event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_events_client_event_id", table_name="usage_events")
    op.drop_column("usage_events", "client_event_id")
