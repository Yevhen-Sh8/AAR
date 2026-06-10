"""NATO LL fields on aar_cases + auto-validation columns on recommendations

Revision ID: 0007_nato_fields
Revises: 0006_context_assets
Create Date: 2026-06-10

Wave 1 of methodology compliance (per docs/PLATFORM.md §6):
- AARCase gets dedicated NATO Lessons Learned fields (what_was_planned,
  what_happened, analysis, lesson_identified, opr) so the Observation →
  LI → LL trail is persisted, not lost on close.
- Recommendation gets `evidence_count` and `auto_validated_at` to support
  the Monitor & Validate stage (services/recommendation_validation.py).
- Existing rows with status='in_progress' are migrated to 'analysed' to
  align with the doctrinal state machine.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_nato_fields"
down_revision: Union[str, None] = "0006_context_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("aar_cases") as batch:
        batch.add_column(sa.Column("what_was_planned", sa.Text(), nullable=True))
        batch.add_column(sa.Column("what_happened", sa.Text(), nullable=True))
        batch.add_column(sa.Column("analysis", sa.Text(), nullable=True))
        batch.add_column(sa.Column("lesson_identified", sa.Text(), nullable=True))
        batch.add_column(sa.Column("opr", sa.String(128), nullable=True))
        batch.add_column(
            sa.Column("analysis_source", sa.String(64), nullable=True)
        )
        batch.add_column(
            sa.Column("analysis_drafted_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.execute(
        "UPDATE aar_cases SET status='analysed' WHERE status='in_progress'"
    )

    with op.batch_alter_table("recommendations") as batch:
        batch.add_column(
            sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("auto_validated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("regressed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("signature", sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_column("signature")
        batch.drop_column("regressed_at")
        batch.drop_column("auto_validated_at")
        batch.drop_column("evidence_count")
    with op.batch_alter_table("aar_cases") as batch:
        batch.drop_column("analysis_drafted_at")
        batch.drop_column("analysis_source")
        batch.drop_column("opr")
        batch.drop_column("lesson_identified")
        batch.drop_column("analysis")
        batch.drop_column("what_happened")
        batch.drop_column("what_was_planned")
