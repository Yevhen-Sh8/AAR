from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator

from aar_api.models.event import Outcome


class UsageEventIn(BaseModel):
    item_serial_no: str
    item_type_code: str
    operator_code: str
    event_date: date
    outcome: Outcome
    loss_reason_code: str | None = None
    repair_reason_code: str | None = None
    notes: str | None = None
    client_event_id: str | None = None
    aborted: bool = False
    abort_reason: str | None = None

    @model_validator(mode="after")
    def _check_reason(self) -> "UsageEventIn":
        if self.outcome == Outcome.LOST and not self.loss_reason_code:
            raise ValueError("loss_reason_code is required when outcome=lost")
        if self.outcome == Outcome.REPAIR and not self.repair_reason_code:
            raise ValueError("repair_reason_code is required when outcome=repair")
        if self.outcome == Outcome.SUCCESS and (
            self.loss_reason_code or self.repair_reason_code
        ):
            raise ValueError("success outcome must not carry a reason")
        return self


class UsageEventListOut(BaseModel):
    """A listed event, with the codes a human reads instead of foreign keys.

    `UsageEventOut` answers the write path, where the client only needs the id
    back. The list is different: this is a PER-SERIAL-NUMBER tracking system,
    and its event list used to render «#24 · #10» — the item and operator row
    ids. Nobody can pick the loss they need to write an act for out of that,
    and the serial number is the whole point of the product.
    """

    model_config = ConfigDict(from_attributes=True)
    id: int
    client_event_id: str | None
    event_date: date
    outcome: Outcome
    item_serial_no: str
    item_type_code: str
    operator_code: str
    loss_reason_code: str | None
    repair_reason_code: str | None
    notes: str | None
    aborted: bool
    abort_reason: str | None
    recorded_at: datetime


class UsageEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_event_id: str | None
    item_id: int
    operator_id: int
    event_date: date
    outcome: Outcome
    loss_reason_id: int | None
    repair_reason_id: int | None
    notes: str | None
    aborted: bool
    abort_reason: str | None
    recorded_at: datetime
