"""append-only audit log with hash-chain

Revision ID: 0005_audit_log
Revises: 0004_integrations
Create Date: 2026-05-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_audit_log"
down_revision: Union[str, None] = "0004_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_table("audit_log")
