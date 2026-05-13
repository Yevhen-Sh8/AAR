from pydantic import BaseModel

from aar_api.models.dictionaries import Zone


class OperatorMonth(BaseModel):
    operator_code: str
    item_type_code: str
    launched: int
    lost: int
    repaired: int
    success: int
    msr: float           # η, Mission Success Rate = success / launched
    msr_c: float         # η_c, Crew-adjusted MSR = success / (launched − ext − mfg losses)
    clr: float           # λ_c, Crew Loss Rate = crew-attributable losses / launched
    delta_msr_pp: float  # Δη vs previous month, in percentage points


class OperatorRating(BaseModel):
    operator_code: str
    msr_c: float
    category: str         # "high" | "ok" | "needs_training"
    rank: int


class ReasonZoneSummary(BaseModel):
    zone: Zone
    losses: int
    repairs: int
    total: int
    share_of_launched: float


class OperatorTrend(BaseModel):
    operator_code: str
    msr_prev: float | None
    msr_this: float
    trend: str            # "up" | "down" | "flat"


class MonthlyReport(BaseModel):
    year: int
    month: int
    rows: list[OperatorMonth]
    totals: OperatorMonth
    rating: list[OperatorRating]
    zones: list[ReasonZoneSummary]
    trends: list[OperatorTrend]
