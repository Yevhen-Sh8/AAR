from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base


class CaseStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


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
    __tablename__ = "aar_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, native_enum=False, length=16), default=CaseStatus.OPEN
    )
    trigger: Mapped[TriggerType] = mapped_column(Enum(TriggerType, native_enum=False, length=32))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id"), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndividualReport(Base):
    __tablename__ = "individual_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("aar_cases.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    what_happened: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_worked: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_failed: Mapped[str | None] = mapped_column(Text, nullable=True)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_to_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Recommendation(Base):
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


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    source_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("aar_cases.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
