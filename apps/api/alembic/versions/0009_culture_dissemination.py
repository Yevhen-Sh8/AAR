"""Wave 3 — anonymous reports, request workflow, notifications

Revision ID: 0009_culture_dissemination
Revises: 0008_learning_kpi
Create Date: 2026-06-10

Wave 3 of methodology compliance (per docs/PLATFORM.md §7):

- IndividualReport gains `anonymous` (TC 25-20 blame-free capture),
  `requested_at` and `requested_for_user_id` (workflow stubs), and both
  `user_id` and `submitted_at` become nullable so the same row can model
  both "we asked X for a report" and "X submitted it anonymously."

- The vestigial `knowledge_entries` table is dropped. The v1.1 Context
  Accumulation Layer (`context_assets`) fully supersedes it; keeping a
  dead model around confuses agents and adds maintenance cost.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_culture_dissemination"
down_revision: Union[str, None] = "0008_learning_kpi"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("individual_reports") as batch:
        batch.add_column(
            sa.Column("anonymous", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "requested_for_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=True,
            )
        )
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("submitted_at", existing_type=sa.DateTime(timezone=True), nullable=True)

    op.drop_table("knowledge_entries")


def downgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_case_id", sa.Integer(), sa.ForeignKey("aar_cases.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    with op.batch_alter_table("individual_reports") as batch:
        batch.alter_column("submitted_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("requested_for_user_id")
        batch.drop_column("requested_at")
        batch.drop_column("anonymous")
