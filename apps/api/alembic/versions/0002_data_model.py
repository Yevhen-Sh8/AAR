"""data model: dictionaries, items, events, AAR cases

Revision ID: 0002_data_model
Revises: 0001_initial
Create Date: 2026-05-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_data_model"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name_uk", sa.String(255), nullable=False),
    )
    op.create_index("ix_item_types_code", "item_types", ["code"], unique=True)

    op.create_table(
        "operators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name_uk", sa.String(255), nullable=False),
    )
    op.create_index("ix_operators_code", "operators", ["code"], unique=True)

    for table in ("loss_reasons", "repair_reasons"):
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(8), nullable=False),
            sa.Column("name_uk", sa.String(255), nullable=False),
            sa.Column("zone", sa.String(16), nullable=False),
        )
        op.create_index(f"ix_{table}_code", table, ["code"], unique=True)

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("serial_no", sa.String(64), nullable=False),
        sa.Column("item_type_id", sa.Integer(), sa.ForeignKey("item_types.id"), nullable=False),
    )
    op.create_index("ix_items_serial_no", "items", ["serial_no"], unique=True)

    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("operators.id"), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("loss_reason_id", sa.Integer(), sa.ForeignKey("loss_reasons.id"), nullable=True),
        sa.Column(
            "repair_reason_id", sa.Integer(), sa.ForeignKey("repair_reasons.id"), nullable=True
        ),
        sa.Column("notes", sa.String(1024), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_usage_events_item_id", "usage_events", ["item_id"])
    op.create_index("ix_usage_events_operator_id", "usage_events", ["operator_id"])
    op.create_index("ix_usage_events_event_date", "usage_events", ["event_date"])

    op.create_table(
        "aar_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("operators.id"), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "individual_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("aar_cases.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("what_happened", sa.Text(), nullable=True),
        sa.Column("what_worked", sa.Text(), nullable=True),
        sa.Column("what_failed", sa.Text(), nullable=True),
        sa.Column("why", sa.Text(), nullable=True),
        sa.Column("external_factors", sa.Text(), nullable=True),
        sa.Column("what_to_change", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_individual_reports_case_id", "individual_reports", ["case_id"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("aar_cases.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recommendations_case_id", "recommendations", ["case_id"])

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


def downgrade() -> None:
    for t in (
        "knowledge_entries",
        "recommendations",
        "individual_reports",
        "aar_cases",
        "usage_events",
        "items",
        "repair_reasons",
        "loss_reasons",
        "operators",
        "item_types",
    ):
        op.drop_table(t)
