"""Webhook subscriptions for outbound integrations (ODIN/DELTA/Kropyva/SAP)."""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base


class ConnectorKind(StrEnum):
    """Recognised target systems. Generic = pure REST/JSON, no specific shape."""

    GENERIC = "generic"
    ODIN = "odin"
    DELTA = "delta"
    KROPYVA = "kropyva"
    SAP = "sap"


class WebhookEventKind(StrEnum):
    USAGE_EVENT_CREATED = "usage_event.created"
    AAR_CASE_CREATED = "aar_case.created"
    AAR_CASE_TRANSITIONED = "aar_case.transitioned"
    AAR_CASE_CLOSED = "aar_case.closed"
    RECOMMENDATION_AUTO_VALIDATED = "recommendation.auto_validated"
    INDIVIDUAL_REPORT_REQUESTED = "individual_report.requested"
    SIGNAL_CREATED = "signal.created"


class Subscription(Base):
    __tablename__ = "integration_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[ConnectorKind] = mapped_column(
        Enum(ConnectorKind, native_enum=False, length=16)
    )
    target_url: Mapped[str] = mapped_column(String(512))
    secret: Mapped[str | None] = mapped_column(String(256), nullable=True)
    events: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class Delivery(Base):
    """Audit trail: every outbound POST attempt is recorded for replay/audit."""

    __tablename__ = "integration_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(Integer)
    event_kind: Mapped[WebhookEventKind] = mapped_column(
        Enum(WebhookEventKind, native_enum=False, length=32)
    )
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, native_enum=False, length=16),
        default=DeliveryStatus.PENDING,
    )
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
