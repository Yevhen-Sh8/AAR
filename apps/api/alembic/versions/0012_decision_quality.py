"""Wave 13: decision quality, judged apart from the outcome (ADR-024).

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0012_decision_quality"
down_revision: str | None = "0011_flexible_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "aar_cases",
        sa.Column(
            "decision_quality",
            sa.String(length=16),
            nullable=False,
            server_default="unassessed",
        ),
    )
    op.add_column(
        "aar_cases", sa.Column("decision_rationale", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("aar_cases", "decision_rationale")
    op.drop_column("aar_cases", "decision_quality")
