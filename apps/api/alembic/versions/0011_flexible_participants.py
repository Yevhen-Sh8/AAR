"""Wave 11 — flexible participants (people directory + per-case function)

Revision ID: 0011_flexible_participants
Revises: 0010_pre_task_signals
Create Date: 2026-07-30

`users` becomes a directory of *persons*: `email` and `hashed_password` are
relaxed to nullable so a roster-only participant (no login account) is a
legal row, guarded by CHECK `hashed_password IS NULL OR email IS NOT NULL`.
Four advisory/derived columns are added (`callsign`, `operator_id`,
`function`, `is_active`).

`individual_reports` gains three evidentiary snapshots (`function`,
`operator_id`, `off_roster`) so per-case function coverage survives
anonymisation and later changes to a person's default function.

NO DATA BACKFILL, deliberately: every new column is nullable or
server-defaulted. Guessing `function='crew'` for existing reports would
poison the exact metric this feature exists to produce — existing rows are
counted in the `"unknown"` coverage bucket instead. That is also what keeps
this migration cleanly reversible.

CAVEAT for future authors: `ck_users_login_needs_email` is invisible to
SQLite reflection, so ANY future `batch_alter_table("users")` will silently
drop it on SQLite (not on Postgres). That is why `downgrade()` guards its
explicit `drop_constraint` with a dialect check.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_flexible_participants"
down_revision: Union[str, None] = "0010_pre_task_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The nullability changes below force SQLite's batch mode to recreate the table
# and copy its existing (unnamed) foreign keys, which fails without names. A
# naming convention lets the reflected constraints be named during the copy.
# On Postgres (production) batch mode runs direct ALTERs and this is a no-op.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade() -> None:
    # ---- users: person directory -----------------------------------------
    with op.batch_alter_table("users", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("callsign", sa.String(64), nullable=True))
        batch.add_column(sa.Column("function", sa.String(32), nullable=True))
        batch.add_column(
            sa.Column(
                "operator_id",
                sa.Integer(),
                sa.ForeignKey(
                    "operators.id",
                    name="fk_users_operator_id_operators",
                    ondelete="SET NULL",
                ),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.alter_column("email", existing_type=sa.String(255), nullable=True)
        batch.alter_column("hashed_password", existing_type=sa.String(255), nullable=True)
        # Yields `ck_users_login_needs_email` via the "ck" convention above.
        batch.create_check_constraint(
            "login_needs_email", "hashed_password IS NULL OR email IS NOT NULL"
        )

    op.create_index("ix_users_operator_id", "users", ["operator_id"])
    op.create_index("ix_users_function", "users", ["function"])
    op.create_index("ix_users_callsign", "users", ["callsign"])
    # The pick-list query: GET /people?suggest_for_case_id=…
    op.create_index("ix_users_operator_function", "users", ["operator_id", "function"])

    # ---- individual_reports: evidentiary snapshots ------------------------
    with op.batch_alter_table(
        "individual_reports", naming_convention=NAMING_CONVENTION
    ) as batch:
        batch.add_column(sa.Column("function", sa.String(32), nullable=True))
        batch.add_column(
            sa.Column(
                "operator_id",
                sa.Integer(),
                sa.ForeignKey(
                    "operators.id",
                    name="fk_individual_reports_operator_id_operators",
                ),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("off_roster", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.create_index("ix_individual_reports_function", "individual_reports", ["function"])
    # The coverage query: GET /aar/report-coverage?case_id=…
    op.create_index(
        "ix_individual_reports_case_function", "individual_reports", ["case_id", "function"]
    )


def downgrade() -> None:
    op.drop_index("ix_individual_reports_case_function", table_name="individual_reports")
    op.drop_index("ix_individual_reports_function", table_name="individual_reports")

    with op.batch_alter_table(
        "individual_reports", naming_convention=NAMING_CONVENTION
    ) as batch:
        batch.drop_column("off_roster")
        batch.drop_column("operator_id")
        batch.drop_column("function")

    op.drop_index("ix_users_operator_function", table_name="users")
    op.drop_index("ix_users_callsign", table_name="users")
    op.drop_index("ix_users_function", table_name="users")
    op.drop_index("ix_users_operator_id", table_name="users")

    # SQLite cannot reflect CHECK constraints: the batch recreate below drops
    # it implicitly there, while an explicit drop_constraint would error.
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("ck_users_login_needs_email", "users", type_="check")

    # NOTE: restoring NOT NULL only succeeds on an empty (or fully
    # credentialled) table. A production downgrade must first delete or
    # complete every credential-less row — see docs/DEPLOY.md.
    with op.batch_alter_table("users", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_column("is_active")
        batch.drop_column("operator_id")
        batch.drop_column("function")
        batch.drop_column("callsign")
        batch.alter_column("hashed_password", existing_type=sa.String(255), nullable=False)
        batch.alter_column("email", existing_type=sa.String(255), nullable=False)
