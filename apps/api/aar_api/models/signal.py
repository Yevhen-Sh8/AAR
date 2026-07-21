"""Pre-task proactive signals (Wave 6).

Implements the "Проактивна взаємодія" concept (docs/concept/positioning.md):
the system is used not only AFTER a task (classic AAR) but BEFORE it — any
user can pre-register a warning, risk, proposal or informational note. These
are routed to responsible persons for review, and can be converted into a
full AAR case when they warrant structured follow-up.

This closes the continuous-learning loop from the concept: conclusions of
previous AARs inform preparation of the next task, and new pre-task
observations feed the centralized experience base.
"""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base


class SignalKind(StrEnum):
    WARNING = "warning"  # попередження про можливий ризик
    RISK = "risk"  # виявлена проблема
    PROPOSAL = "proposal"  # пропозиція щодо покращення
    INFO = "info"  # інформаційний сигнал


class SignalStatus(StrEnum):
    """Minimal review lifecycle.

    NEW          — submitted, awaiting review
    ACKNOWLEDGED — seen by a responsible person, under consideration
    ACCEPTED     — acted upon (change made during preparation)
    DISMISSED    — reviewed and consciously declined (reason recorded)
    CONVERTED    — escalated into a full AAR case (case_id set)
    """

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    CONVERTED = "converted"


class PreTaskSignal(Base):
    __tablename__ = "pre_task_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[SignalKind] = mapped_column(
        Enum(SignalKind, native_enum=False, length=16), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text author; nullable so signals can be submitted anonymously
    # (same TC 25-20 blame-free rationale as IndividualReport.anonymous).
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Optional context: which upcoming task/mission this concerns.
    task_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus, native_enum=False, length=16),
        default=SignalStatus.NEW,
        index=True,
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("aar_cases.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
