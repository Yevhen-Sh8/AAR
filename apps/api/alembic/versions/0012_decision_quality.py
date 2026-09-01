"""Wave 13: decision quality, judged apart from the outcome (ADR-024).

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
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
