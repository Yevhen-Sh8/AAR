from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base


class Outcome(StrEnum):
    SUCCESS = "success"
    LOST = "lost"
    REPAIR = "repair"


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    item_type_id: Mapped[int] = mapped_column(ForeignKey("item_types.id"))


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_event_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    outcome: Mapped[Outcome] = mapped_column(Enum(Outcome, native_enum=False, length=16))
    loss_reason_id: Mapped[int | None] = mapped_column(
        ForeignKey("loss_reasons.id"), nullable=True
    )
    repair_reason_id: Mapped[int | None] = mapped_column(
        ForeignKey("repair_reasons.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    location: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Wave 2: distinguishes "launched and succeeded/failed" from "aborted
    # before reaching target" (EW jam, weather, pre-flight technical scrub).
    # narrow MSR  = success / launched     (only non-aborted)
    # full   MSR  = success / (launched + aborted)
    # See literature note in docs/metrics.md §3.
    aborted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    abort_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
