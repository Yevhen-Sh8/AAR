from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from aar_api.models.integration import ConnectorKind, DeliveryStatus, WebhookEventKind


class GeoJSONPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: list[float] = Field(min_length=2, max_length=3)


class SubscriptionIn(BaseModel):
    name: str
    kind: ConnectorKind = ConnectorKind.GENERIC
    target_url: HttpUrl
    secret: str | None = None
    events: list[WebhookEventKind]
    headers: dict[str, str] | None = None
    active: bool = True


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: ConnectorKind
    target_url: str
    events: list[WebhookEventKind]
    active: bool
    created_at: datetime


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subscription_id: int
    event_kind: WebhookEventKind
    status: DeliveryStatus
    response_code: int | None
    error: str | None
    attempts: int
    dispatched_at: datetime


class InboundEvent(BaseModel):
    """Normalised inbound envelope from any source system."""

    source: str
    external_id: str | None = None
    item_serial_no: str
    item_type_code: str
    operator_code: str
    event_date: str
    outcome: Literal["success", "lost", "repair"]
    loss_reason_code: str | None = None
    repair_reason_code: str | None = None
    location: GeoJSONPoint | None = None
    notes: str | None = None
