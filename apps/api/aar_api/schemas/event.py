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
    recorded_at: datetime
