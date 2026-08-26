from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from aar_api.models.aar import AARCase, Recommendation, RecommendationStatus
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.schemas.reports import (
    DailyConclusions,
    DailyReport,
    DailyRow,
    LossDetail,
    LossReasonBreakdown,
    RepairDetail,
    RepairReasonBreakdown,
)


def _msr(success: int, launched: int) -> float:
    return round(success / launched, 4) if launched else 0.0


async def build_daily_report(session: AsyncSession, report_date: date) -> DailyReport:
    LR = aliased(LossReason)
    RR = aliased(RepairReason)
    stmt = (
        select(
            UsageEvent.id,
            Operator.code.label("operator_code"),
            ItemType.code.label("item_type_code"),
            Item.serial_no,
            UsageEvent.outcome,
            LR.code.label("loss_code"),
            LR.zone.label("loss_zone"),
            RR.code.label("repair_code"),
            RR.zone.label("repair_zone"),
            UsageEvent.notes,
        )
        .join(Operator, Operator.id == UsageEvent.operator_id)
        .join(Item, Item.id == UsageEvent.item_id)
        .join(ItemType, ItemType.id == Item.item_type_id)
        .join(LR, LR.id == UsageEvent.loss_reason_id, isouter=True)
        .join(RR, RR.id == UsageEvent.repair_reason_id, isouter=True)
        .where(UsageEvent.event_date == report_date)
    )
    events = list(await session.execute(stmt))

    bucket: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"launched": 0, "lost": 0, "repaired": 0, "success": 0}
    )
    loss_details: list[LossDetail] = []
    repair_details: list[RepairDetail] = []
    loss_break: dict[tuple[str, str], LossReasonBreakdown] = {}
    repair_break: dict[tuple[str, str], RepairReasonBreakdown] = {}

    for row in events:
        key = (row.operator_code, row.item_type_code)
        bucket[key]["launched"] += 1
        if row.outcome == Outcome.LOST:
            bucket[key]["lost"] += 1
            loss_details.append(
                LossDetail(
                    operator_code=row.operator_code,
                    item_type_code=row.item_type_code,
                    serial_no=row.serial_no,
                    reason_code=row.loss_code or "?",
                    notes=row.notes,
                )
            )
            bk = (row.item_type_code, row.loss_code or "?")
            if bk in loss_break:
                loss_break[bk] = loss_break[bk].model_copy(
                    update={"count": loss_break[bk].count + 1}
                )
            else:
                loss_break[bk] = LossReasonBreakdown(
                    item_type_code=bk[0], reason_code=bk[1], zone=row.loss_zone, count=1
                )
        elif row.outcome == Outcome.REPAIR:
            bucket[key]["repaired"] += 1
            repair_details.append(
                RepairDetail(
                    operator_code=row.operator_code,
                    item_type_code=row.item_type_code,
                    serial_no=row.serial_no,
                    reason_code=row.repair_code or "?",
                    notes=row.notes,
                )
            )
            bk = (row.item_type_code, row.repair_code or "?")
            if bk in repair_break:
                repair_break[bk] = repair_break[bk].model_copy(
                    update={"count": repair_break[bk].count + 1}
                )
            else:
                repair_break[bk] = RepairReasonBreakdown(
                    item_type_code=bk[0], reason_code=bk[1], zone=row.repair_zone, count=1
                )
        else:
            bucket[key]["success"] += 1

    rows: list[DailyRow] = []
    totals = {"launched": 0, "lost": 0, "repaired": 0, "success": 0}
    for (op_code, type_code), counts in sorted(bucket.items()):
        rows.append(
            DailyRow(
                operator_code=op_code,
                item_type_code=type_code,
                launched=counts["launched"],
                lost=counts["lost"],
                repaired=counts["repaired"],
                success=counts["success"],
                msr=_msr(counts["success"], counts["launched"]),
            )
        )
        for k in totals:
            totals[k] += counts[k]

    totals_row = DailyRow(
        operator_code="TOTAL",
        item_type_code="ALL",
        launched=totals["launched"],
        lost=totals["lost"],
        repaired=totals["repaired"],
        success=totals["success"],
        msr=_msr(totals["success"], totals["launched"]),
    )
    conclusions = await _build_conclusions(
        session,
        report_date,
        totals_row,
        sorted(loss_break.values(), key=lambda b: -b.count),
        sorted(repair_break.values(), key=lambda b: -b.count),
    )

    return DailyReport(
        report_date=report_date,
        rows=rows,
        totals=totals_row,
        loss_details=sorted(loss_details, key=lambda d: (d.operator_code, d.serial_no)),
        loss_breakdown=sorted(loss_break.values(), key=lambda b: (b.item_type_code, b.reason_code)),
        repair_details=sorted(repair_details, key=lambda d: (d.operator_code, d.serial_no)),
        repair_breakdown=sorted(
            repair_break.values(), key=lambda b: (b.item_type_code, b.reason_code)
        ),
        conclusions=conclusions,
    )


async def _build_conclusions(
    session: AsyncSession,
    report_date: date,
    totals: DailyRow,
    losses_sorted: list[LossReasonBreakdown],
    repairs_sorted: list[RepairReasonBreakdown],
) -> DailyConclusions:
    """Generate the 'Висновки доби' block per docs/forms/daily-template.md §2."""
    top_losses = [
        f"{b.reason_code} (×{b.count}) — {b.zone.value}" for b in losses_sorted[:3]
    ]
    top_repairs = [
        f"{b.reason_code} (×{b.count}) — {b.zone.value}" for b in repairs_sorted[:3]
    ]

    day_start = datetime.combine(report_date, time.min)
    day_end = day_start + timedelta(days=1)
    cases_today = list(
        await session.scalars(
            select(AARCase).where(
                AARCase.opened_at >= day_start,
                AARCase.opened_at < day_end,
            )
        )
    )
    triggers = [c.title for c in cases_today]

    open_recs = await session.scalar(
        select(func.count(Recommendation.id)).where(
            Recommendation.status.in_(
                [RecommendationStatus.PROPOSED, RecommendationStatus.IN_PROGRESS]
            )
        )
    )

    headline = (
        f"Успішність {totals.msr * 100:.1f}%, запущено {totals.launched}, "
        f"успіх {totals.success}, втрат {totals.lost}, ремонт {totals.repaired}."
    )
    if not triggers and totals.lost == 0:
        headline += " Доба без інцидентів."
    elif triggers:
        headline += f" Активних тригерів: {len(triggers)}."

    return DailyConclusions(
        top_loss_reasons=top_losses or ["—"],
        top_repair_reasons=top_repairs or ["—"],
        active_triggers=triggers,
        open_recommendations=int(open_recs or 0),
        headline=headline,
    )
