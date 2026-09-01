"""Wave 13: knowledge ages by category (ADR-025).

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "context_assets",
        sa.Column("last_affirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "context_assets",
        sa.Column("affirmed_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "context_assets", sa.Column("review_after_days", sa.Integer(), nullable=True)
    )
    # Seed the clock from the original validation so existing assets age from
    # when a person actually confirmed them, not from the deploy.
    op.execute(
        "UPDATE context_assets SET last_affirmed_at = validated_at "
        "WHERE validated_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("context_assets", "review_after_days")
    op.drop_column("context_assets", "affirmed_count")
    op.drop_column("context_assets", "last_affirmed_at")
