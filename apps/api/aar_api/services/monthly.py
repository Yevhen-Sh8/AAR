from calendar import monthrange
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason, Zone
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.schemas.monthly import (
    MonthlyReport,
    OperatorMonth,
    OperatorRating,
    OperatorTrend,
    ReasonZoneSummary,
)

HIGH_THRESHOLD = 0.85
OK_THRESHOLD = 0.70


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _category(keff_obsl: float) -> str:
    if keff_obsl >= HIGH_THRESHOLD:
        return "high"
    if keff_obsl >= OK_THRESHOLD:
        return "ok"
    return "needs_training"


async def _fetch_rows(session: AsyncSession, year: int, month: int) -> list:
    start, end = _month_bounds(year, month)
    LR = aliased(LossReason)
    RR = aliased(RepairReason)
    stmt = (
        select(
            Operator.code.label("operator_code"),
            ItemType.code.label("item_type_code"),
            UsageEvent.outcome,
            LR.zone.label("loss_zone"),
            RR.zone.label("repair_zone"),
        )
        .join(Operator, Operator.id == UsageEvent.operator_id)
        .join(Item, Item.id == UsageEvent.item_id)
        .join(ItemType, ItemType.id == Item.item_type_id)
        .join(LR, LR.id == UsageEvent.loss_reason_id, isouter=True)
        .join(RR, RR.id == UsageEvent.repair_reason_id, isouter=True)
        .where(UsageEvent.event_date.between(start, end))
    )
    return list(await session.execute(stmt))


def _zero() -> dict[str, int]:
    return {
        "launched": 0,
        "lost": 0,
        "repaired": 0,
        "success": 0,
        "lost_op": 0,        # losses with operator zone
        "lost_external": 0,  # losses with external zone
        "lost_mfg": 0,       # losses with manufacturer zone
        "rep_op": 0,
        "rep_external": 0,
        "rep_mfg": 0,
    }


def _accumulate(bucket: dict, key: tuple[str, str], row: object) -> None:
    b = bucket.setdefault(key, _zero())
    b["launched"] += 1
    outcome = row.outcome  # type: ignore[attr-defined]
    if outcome == Outcome.LOST:
        b["lost"] += 1
        zone = row.loss_zone  # type: ignore[attr-defined]
        if zone == Zone.OPERATOR:
            b["lost_op"] += 1
        elif zone == Zone.EXTERNAL:
            b["lost_external"] += 1
        elif zone == Zone.MANUFACTURER:
            b["lost_mfg"] += 1
    elif outcome == Outcome.REPAIR:
        b["repaired"] += 1
        zone = row.repair_zone  # type: ignore[attr-defined]
        if zone == Zone.OPERATOR:
            b["rep_op"] += 1
        elif zone == Zone.EXTERNAL:
            b["rep_external"] += 1
        elif zone == Zone.MANUFACTURER:
            b["rep_mfg"] += 1
    else:
        b["success"] += 1


def _round(value: float) -> float:
    return round(value, 4)


def _operator_month(operator_code: str, item_type_code: str, c: dict[str, int],
                    prev_keff: float | None) -> OperatorMonth:
    launched = c["launched"]
    success = c["success"]
    keff = _round(success / launched) if launched else 0.0
    not_operator = c["lost_external"] + c["lost_mfg"]
    cleaned = launched - not_operator
    keff_obsl = _round(success / cleaned) if cleaned else 0.0
    op_losses = c["lost_op"] + c["rep_op"]
    kv_obsl = _round(op_losses / launched) if launched else 0.0
    delta_pp = _round((keff - prev_keff) * 100) if prev_keff is not None else 0.0
    return OperatorMonth(
        operator_code=operator_code,
        item_type_code=item_type_code,
        launched=launched,
        lost=c["lost"],
        repaired=c["repaired"],
        success=success,
        keff=keff,
        keff_obsl=keff_obsl,
        kv_obsl=kv_obsl,
        delta_keff_pp=delta_pp,
    )


async def build_monthly_report(session: AsyncSession, year: int, month: int) -> MonthlyReport:
    rows_db = await _fetch_rows(session, year, month)
    bucket: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows_db:
        _accumulate(bucket, (row.operator_code, row.item_type_code), row)

    py, pm = _prev_month(year, month)
    prev_rows_db = await _fetch_rows(session, py, pm)
    prev_bucket: dict[tuple[str, str], dict[str, int]] = {}
    for row in prev_rows_db:
        _accumulate(prev_bucket, (row.operator_code, row.item_type_code), row)

    def _prev_keff(key: tuple[str, str]) -> float | None:
        p = prev_bucket.get(key)
        if p is None or not p["launched"]:
            return None
        return p["success"] / p["launched"]

    rows: list[OperatorMonth] = []
    totals = _zero()
    for key, counts in sorted(bucket.items()):
        rows.append(_operator_month(key[0], key[1], counts, _prev_keff(key)))
        for k in totals:
            totals[k] += counts[k]
    totals_row = _operator_month("TOTAL", "ALL", totals, None)

    # Rating per operator across all types
    by_op: dict[str, dict[str, int]] = defaultdict(_zero)
    for (op_code, _), counts in bucket.items():
        for k in by_op[op_code]:
            by_op[op_code][k] += counts[k]
    rating_rows: list[OperatorRating] = []
    for op_code, c in by_op.items():
        cleaned = c["launched"] - c["lost_external"] - c["lost_mfg"]
        keff_obsl = _round(c["success"] / cleaned) if cleaned else 0.0
        rating_rows.append(
            OperatorRating(operator_code=op_code, keff_obsl=keff_obsl,
                           category=_category(keff_obsl), rank=0)
        )
    rating_rows.sort(key=lambda r: (-r.keff_obsl, r.operator_code))
    for i, row in enumerate(rating_rows, start=1):
        row.rank = i

    # Zone summary across enterprise
    zone_acc: dict[Zone, dict[str, int]] = {z: {"losses": 0, "repairs": 0} for z in Zone}
    for row in rows_db:
        if row.outcome == Outcome.LOST and row.loss_zone:
            zone_acc[row.loss_zone]["losses"] += 1
        elif row.outcome == Outcome.REPAIR and row.repair_zone:
            zone_acc[row.repair_zone]["repairs"] += 1
    zones: list[ReasonZoneSummary] = []
    for z, c in zone_acc.items():
        total = c["losses"] + c["repairs"]
        zones.append(
            ReasonZoneSummary(
                zone=z, losses=c["losses"], repairs=c["repairs"], total=total,
                share_of_launched=_round(total / totals["launched"]) if totals["launched"] else 0.0,
            )
        )

    # Trends per operator (any type)
    this_op: dict[str, dict[str, int]] = defaultdict(_zero)
    prev_op: dict[str, dict[str, int]] = defaultdict(_zero)
    for (op_code, _), c in bucket.items():
        for k in this_op[op_code]:
            this_op[op_code][k] += c[k]
    for (op_code, _), c in prev_bucket.items():
        for k in prev_op[op_code]:
            prev_op[op_code][k] += c[k]
    trends: list[OperatorTrend] = []
    for op_code, c in this_op.items():
        this_keff = _round(c["success"] / c["launched"]) if c["launched"] else 0.0
        p = prev_op.get(op_code)
        prev_keff_value: float | None = None
        if p and p["launched"]:
            prev_keff_value = _round(p["success"] / p["launched"])
        if prev_keff_value is None:
            label = "flat"
        elif this_keff > prev_keff_value:
            label = "up"
        elif this_keff < prev_keff_value:
            label = "down"
        else:
            label = "flat"
        trends.append(
            OperatorTrend(operator_code=op_code, keff_prev_month=prev_keff_value,
                          keff_this_month=this_keff, trend=label)
        )
    trends.sort(key=lambda t: t.operator_code)

    return MonthlyReport(
        year=year, month=month, rows=rows, totals=totals_row,
        rating=rating_rows, zones=zones, trends=trends,
    )
