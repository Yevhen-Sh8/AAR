from pydantic import BaseModel

from aar_api.models.dictionaries import Zone


class OperatorMonth(BaseModel):
    operator_code: str
    item_type_code: str
    launched: int
    lost: int
    repaired: int
    success: int
    keff: float           # У / З
    keff_obsl: float      # У / (З − зовнішні − виробничі)
    kv_obsl: float        # втрати "зони обслуги" / З
    delta_keff_pp: float  # vs попередній місяць, у відсоткових пунктах


class OperatorRating(BaseModel):
    operator_code: str
    keff_obsl: float
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
    keff_prev_month: float | None
    keff_this_month: float
    trend: str            # "up" | "down" | "flat"


class MonthlyReport(BaseModel):
    year: int
    month: int
    rows: list[OperatorMonth]
    totals: OperatorMonth
    rating: list[OperatorRating]
    zones: list[ReasonZoneSummary]
    trends: list[OperatorTrend]
