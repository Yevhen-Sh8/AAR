from datetime import date

from pydantic import BaseModel

from aar_api.models.dictionaries import Zone


class DailyRow(BaseModel):
    operator_code: str
    item_type_code: str
    launched: int
    lost: int
    repaired: int
    success: int
    msr: float  # Mission Success Rate, η = success / launched


class LossReasonBreakdown(BaseModel):
    item_type_code: str
    reason_code: str
    zone: Zone
    count: int


class RepairReasonBreakdown(BaseModel):
    item_type_code: str
    reason_code: str
    zone: Zone
    count: int


class LossDetail(BaseModel):
    operator_code: str
    item_type_code: str
    serial_no: str
    reason_code: str
    notes: str | None = None


class RepairDetail(BaseModel):
    operator_code: str
    item_type_code: str
    serial_no: str
    reason_code: str
    notes: str | None = None


class DailyReport(BaseModel):
    report_date: date
    rows: list[DailyRow]
    totals: DailyRow
    loss_details: list[LossDetail]
    loss_breakdown: list[LossReasonBreakdown]
    repair_details: list[RepairDetail]
    repair_breakdown: list[RepairReasonBreakdown]
