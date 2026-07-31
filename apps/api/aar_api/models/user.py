"""People directory.

Wave 11 turns `users` from a table of *principals* into a table of *persons*,
some of whom can also authenticate. A person with no `hashed_password` (and
possibly no `email`) is a roster-only participant: they can be picked as an
AAR participant, receive report requests and be credited on submitted reports,
but they cannot log in. Promotion to a login account is a single UPDATE on the
same row — every historical FK (`individual_reports.user_id`,
`individual_reports.requested_for_user_id`, `context_assets.validated_by_user_id`)
stays valid.

Consequence to keep in mind: any "how many users do we have" metric must now
filter on `can_login`, and nothing may assume `user.email` is non-null.
"""
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base


class Role(StrEnum):
    """Authorisation role — what the person may do in the *system*."""

    PARTICIPANT = "participant"
    ANALYST = "analyst"
    MANAGER = "manager"
    ADMIN = "admin"
    INTEGRATOR = "integrator"


class ParticipantFunction(StrEnum):
    """Field function — what the person did in the *event*.

    Strictly orthogonal to `Role`: an `admin` may be a `crew` member and a
    `participant` may be the `commander`. Never merge the two, never derive
    one from the other.

    The loss-zone model (operator / manufacturer / external) can only be
    attributed fairly when testimony comes from different functions —
    otherwise the crew is blamed by default.
    """

    CREW = "crew"  # екіпаж / оператор
    ENGINEERING = "engineering"  # інженерно-технічна обслуга
    COMMANDER = "commander"  # начальник розрахунку / командир групи
    EW_RECON = "ew_recon"  # РЕБ / розвідка
    MANUFACTURER = "manufacturer"  # представник виробника
    OTHER = "other"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable since Wave 11 — a roster-only person may have no email at all.
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    # Nullable since Wave 11 — absence of credentials *is* how "cannot log in"
    # is modelled. See routers/auth.py: the login path must guard against None.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=32), default=Role.PARTICIPANT
    )

    # ---- Wave 11: advisory affiliation + default field function -----------
    # Both are *suggestions* only. Nothing anywhere relates `operator_id` to
    # `aar_cases.operator_id` — no FK, no CHECK, no validator. Affiliation may
    # appear in ORDER BY, never in an implicit WHERE.
    callsign: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("operators.id", ondelete="SET NULL"), nullable=True, index=True
    )
    function: Mapped[ParticipantFunction | None] = mapped_column(
        Enum(ParticipantFunction, native_enum=False, length=32), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "hashed_password IS NULL OR email IS NOT NULL",
            name="ck_users_login_needs_email",
        ),
        Index("ix_users_operator_function", "operator_id", "function"),
    )

    @property
    def can_login(self) -> bool:
        """Derived, never stored — a credentialled, addressable, active row."""
        return bool(self.hashed_password and self.email and self.is_active)
