from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base


class CaseStatus(StrEnum):
    """Doctrinal NATO LL state machine.

    Maps to NATO Lessons Learned Process (LLH4):
        OPEN       — Observation captured, Issue identified
        ANALYSED   — Discussion+Analysis done, Lesson Identified
        ENDORSED   — Leadership tasked OPR with remedial action
        IMPLEMENTED — Remedial action executed
        VALIDATED  — Monitor & Validate confirmed fix → Lesson Learned
        CLOSED     — Institutionalised / archived

    Legacy values (`in_progress`) are migrated to ANALYSED in migration 0007.
    """

    OPEN = "open"
    ANALYSED = "analysed"
    ENDORSED = "endorsed"
    IMPLEMENTED = "implemented"
    VALIDATED = "validated"
    CLOSED = "closed"


# Allowed forward transitions per NATO LL cycle. Backward moves require
# explicit `force=True` (used by auto-regression on T2 recurrence).
ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.OPEN: {CaseStatus.ANALYSED, CaseStatus.CLOSED},
    CaseStatus.ANALYSED: {CaseStatus.ENDORSED, CaseStatus.OPEN, CaseStatus.CLOSED},
    CaseStatus.ENDORSED: {CaseStatus.IMPLEMENTED, CaseStatus.ANALYSED},
    CaseStatus.IMPLEMENTED: {CaseStatus.VALIDATED, CaseStatus.ENDORSED},
    CaseStatus.VALIDATED: {CaseStatus.CLOSED, CaseStatus.IMPLEMENTED},
    CaseStatus.CLOSED: set(),
}


class TriggerType(StrEnum):
    MANUAL = "manual"
    MSR_DROP = "msr_drop"  # T1: MSR_c below threshold N consecutive days
    REPEATED_REASON = "repeated_reason"  # T2
    ITEM_ANOMALY = "item_anomaly"  # T3
    ENTERPRISE_DROP = "enterprise_drop"  # T4: enterprise MSR drop d-o-d


class RecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    VALIDATED = "validated"


class AARCase(Base):
    """AAR case carrying the full NATO LL trail.

    See docs/PLATFORM.md §3 for the field-to-stage mapping.
    """

    __tablename__ = "aar_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, native_enum=False, length=16), default=CaseStatus.OPEN
    )
    trigger: Mapped[TriggerType] = mapped_column(Enum(TriggerType, native_enum=False, length=32))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id"), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # NATO LL fields — added in 0007. Each maps to one AAR question / LL stage.
    what_was_planned: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_happened: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)  # the "why"
    lesson_identified: Mapped[str | None] = mapped_column(Text, nullable=True)
    # opr = Office of Primary Responsibility (NATO LL endorse stage)
    opr: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Provenance of the analysis text — "llm:claude-sonnet-4-6", "manual", "edited" etc.
    analysis_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_drafted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Wave 2: stamped on transition to VALIDATED. Lets the learning-loop
    # service compute median time_to_validation = validated_at - opened_at.
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndividualReport(Base):
    """Per-participant AAR report. Supports both flows:

    Pending-request: a manager asks N users for a report → N stub rows are
    created with `requested_at` set, `user_id`/`submitted_at` null. The user
    later fills them in.

    Anonymous submission (TC 25-20 culture): when `anonymous=True`, the
    response API redacts `user_id` to viewers without admin role, but the
    audit chain still records the originator. This preserves blame-free
    capture without losing the audit trail.
    """

    __tablename__ = "individual_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("aar_cases.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    requested_for_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    what_happened: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_worked: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_failed: Mapped[str | None] = mapped_column(Text, nullable=True)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_to_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Recommendation(Base):
    """Remedial action proposed by an AAR case.

    Auto-validation (per services/recommendation_validation.py):
      - `signature` ties the recommendation to a trigger pattern (e.g. T2:loss:c).
      - When the engine runs and that signature does NOT recur for N days after
        `DONE`, `auto_validated_at` is set and status flips to VALIDATED.
      - If the signature DOES recur, status regresses to IN_PROGRESS and
        `regressed_at` is stamped. This kills the "lessons observed ≠ lessons
        learned" gap (literature failure mode #1).
    """

    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("aar_cases.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus, native_enum=False, length=16),
        default=RecommendationStatus.PROPOSED,
    )
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    auto_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    regressed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    signature: Mapped[str | None] = mapped_column(String(128), nullable=True)


# KnowledgeEntry was removed in Wave 3 (migration 0009). It was the legacy v1.0
# Lessons Learned store, fully superseded by ContextAsset (v1.1 CAL). The old
# model was orphan code — no router wrote to it — and confused agents reading
# the codebase. See ADR-014.
