"""Wave 2 — learning-loop KPIs: aborts, unit cost, validated_at stamp

Revision ID: 0008_learning_kpi
Revises: 0007_nato_fields
Create Date: 2026-06-10

Wave 2 of methodology compliance (per docs/PLATFORM.md §7).

- usage_events gets `aborted` (bool) and `abort_reason` (text) so we can
  compute MSR-narrow (success / launched) vs MSR-full (success / (launched
  + aborted)) — the literature insists on tracking both denominators
  (narrow ~43%, full ~20–30% in the dronesphere literature).
- item_types gets `unit_cost_usd` (numeric) so cost-per-effect is
  computable straight from the events.
- aar_cases gets `validated_at` — stamped automatically by the transition
  endpoint when the target is VALIDATED. Lets us compute the headline
  meta-KPI: median time_to_validation = validated_at − opened_at.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_learning_kpi"
down_revision: Union[str, None] = "0007_nato_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usage_events") as batch:
        batch.add_column(
            sa.Column("aborted", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("abort_reason", sa.String(64), nullable=True))

    with op.batch_alter_table("item_types") as batch:
        batch.add_column(sa.Column("unit_cost_usd", sa.Numeric(10, 2), nullable=True))

    with op.batch_alter_table("aar_cases") as batch:
        batch.add_column(sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("aar_cases") as batch:
        batch.drop_column("validated_at")
    with op.batch_alter_table("item_types") as batch:
        batch.drop_column("unit_cost_usd")
    with op.batch_alter_table("usage_events") as batch:
        batch.drop_column("abort_reason")
        batch.drop_column("aborted")
