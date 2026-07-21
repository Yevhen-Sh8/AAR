"""Wave 6 — pre-task proactive signals

Revision ID: 0010_pre_task_signals
Revises: 0009_culture_dissemination
Create Date: 2026-07-19

Implements the "Проактивна взаємодія" concept (docs/concept/positioning.md):
signals submitted BEFORE task execution (warning / risk / proposal / info),
with a minimal review lifecycle and optional escalation into an AAR case.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_pre_task_signals"
down_revision: Union[str, None] = "0009_culture_dissemination"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pre_task_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("author", sa.String(128), nullable=True),
        sa.Column("task_context", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "case_id",
            sa.Integer(),
            sa.ForeignKey("aar_cases.id", name="fk_pre_task_signals_case_id_aar_cases"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pre_task_signals_kind", "pre_task_signals", ["kind"])
    op.create_index("ix_pre_task_signals_status", "pre_task_signals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pre_task_signals_status", table_name="pre_task_signals")
    op.drop_index("ix_pre_task_signals_kind", table_name="pre_task_signals")
    op.drop_table("pre_task_signals")
