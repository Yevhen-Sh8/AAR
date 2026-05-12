"""Append-only audit log with cryptographic hash-chain.

Each row carries `prev_hash` of the previous row and `entry_hash` of itself
(SHA-256 over canonical JSON of action+actor+entity+payload+prev_hash).
Tampering with any historical row breaks the chain — `verify_chain()` walks
the table and returns the index of the first divergence.

Realises automation scenario A12 from docs/automation.md and the audit-trail
control mandated by ISO/IEC 27001:2022 Annex A (A.8 logging).
"""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base


class AuditAction(StrEnum):
    EVENT_CREATED = "event.created"
    EVENT_INBOUND = "event.inbound"
    CASE_CREATED = "case.created"
    CASE_CLOSED = "case.closed"
    RECOMMENDATION_UPDATED = "recommendation.updated"
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_DELETED = "subscription.deleted"
    TRIGGERS_RUN = "triggers.run"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, native_enum=False, length=64), index=True
    )
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
