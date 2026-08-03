"""Meta-KPI of the lessons-learned loop itself (Wave 2).

The literature names "no measurable benefit" as the #2 reason LL programs die
— leadership stops sponsoring something it cannot prove is working. This
service computes the headline numbers that show the loop is alive:

    time_to_validation_days_median     how fast does an Issue become a Lesson?
    li_to_ll_conversion_pct            of analysed cases, how many graduate?
    recurrence_rate_pct                of validated recs, how many regressed?
    open_cases_by_opr                  workload pressure per responsible body
    msr_narrow / msr_full              both denominators per literature norm
    cost_per_effect_usd                cheap-mass arithmetic by item type

Inputs come straight from the existing tables; no LLM here.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.models.aar import (
    AARCase,
    CaseStatus,
    Recommendation,
    RecommendationStatus,
)
from aar_api.models.dictionaries import ItemType
from aar_api.models.event import Item, Outcome, UsageEvent


@dataclass(frozen=True)
class LoopKPI:
    # Cycle speed
    time_to_validation_days_median: float | None
    time_to_validation_days_p90: float | None
    cases_with_validation: int

    # Conversion
    li_to_ll_conversion_pct: float
    cases_analysed_or_later: int
    cases_validated_or_closed: int

    # Recurrence (failure-mode tracking)
    recurrence_rate_pct: float
    regressed_recommendations: int
    validated_recommendations: int

    # OPR load
    open_cases_by_opr: dict[str, int]

    # Effectiveness denominators (literature insists on both)
    msr_narrow: float
    msr_full: float
    launched_count: int
    aborted_count: int
    success_count: int

    # Cheap-mass arithmetic
    cost_per_effect_usd_by_type: dict[str, float]

    period_from: datetime
    period_to: datetime


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * pct
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


async def compute_loop_kpi(
    session: AsyncSession,
    period_from: datetime | None = None,
    period_to: datetime | None = None,
) -> LoopKPI:
    """Compute the learning-loop KPI snapshot.

    period_from/period_to filter UsageEvent + case-open windows. Defaults to
    the last 90 days, ending now.
    """
    now = datetime.now(UTC)
    period_to = period_to or now
    period_from = period_from or (period_to - timedelta(days=90))

    # ─────────────── Cycle speed ───────────────
    # Both bounds: the docstring promises period_to filters the case-open
    # window too, but only the lower bound was applied — so asking for a
    # historical window still folded in every case opened after it, quietly
    # inflating time-to-validation, LI→LL conversion and OPR load.
    case_rows = list(
        await session.scalars(
            select(AARCase).where(
                AARCase.opened_at >= period_from,
                AARCase.opened_at <= period_to,
            )
        )
    )
    ttv: list[float] = []
    for c in case_rows:
        if c.validated_at is not None:
            delta = c.validated_at - c.opened_at
            ttv.append(delta.total_seconds() / 86400.0)

    # ─────────────── LI → LL conversion ───────────────
    analysed_or_later = {
        CaseStatus.ANALYSED,
        CaseStatus.ENDORSED,
        CaseStatus.IMPLEMENTED,
        CaseStatus.VALIDATED,
        CaseStatus.CLOSED,
    }
    li_count = sum(1 for c in case_rows if c.status in analysed_or_later)
    ll_count = sum(
        1 for c in case_rows if c.status in {CaseStatus.VALIDATED, CaseStatus.CLOSED}
    )
    li_to_ll = (ll_count / li_count * 100.0) if li_count else 0.0

    # ─────────────── Recurrence ───────────────
    rec_rows = list(await session.scalars(select(Recommendation)))
    validated_recs = sum(
        1 for r in rec_rows
        if r.status == RecommendationStatus.VALIDATED or r.auto_validated_at is not None
    )
    regressed_recs = sum(1 for r in rec_rows if r.regressed_at is not None)
    recurrence_pct = (regressed_recs / validated_recs * 100.0) if validated_recs else 0.0

    # ─────────────── OPR load ───────────────
    opr_load: dict[str, int] = defaultdict(int)
    for c in case_rows:
        if c.status == CaseStatus.CLOSED:
            continue
        key = c.opr or "не призначено"
        opr_load[key] += 1

    # ─────────────── Effectiveness ───────────────
    ev_rows = list(
        await session.scalars(
            select(UsageEvent).where(
                UsageEvent.event_date >= period_from.date(),
                UsageEvent.event_date <= period_to.date(),
            )
        )
    )
    launched = sum(1 for e in ev_rows if not e.aborted)
    aborted = sum(1 for e in ev_rows if e.aborted)
    success = sum(1 for e in ev_rows if not e.aborted and e.outcome == Outcome.SUCCESS)
    msr_narrow = (success / launched) if launched else 0.0
    msr_full = (success / (launched + aborted)) if (launched + aborted) else 0.0

    # ─────────────── Cost per effect ───────────────
    # Need item_type for each event → join via items.
    type_rows = {it.id: it for it in (await session.scalars(select(ItemType))).all()}
    items_map = {it.id: it for it in (await session.scalars(select(Item))).all()}
    by_type_cost: dict[str, tuple[Decimal, int]] = defaultdict(lambda: (Decimal("0"), 0))
    for e in ev_rows:
        item = items_map.get(e.item_id)
        if item is None:
            continue
        it = type_rows.get(item.item_type_id)
        if it is None or it.unit_cost_usd is None:
            continue
        total, succ = by_type_cost[it.code]
        new_total = total + Decimal(it.unit_cost_usd)
        new_succ = succ + (1 if (not e.aborted and e.outcome == Outcome.SUCCESS) else 0)
        by_type_cost[it.code] = (new_total, new_succ)
    cost_per_effect: dict[str, float] = {}
    for code, (total, succ) in by_type_cost.items():
        if succ > 0:
            cost_per_effect[code] = float(total / succ)

    return LoopKPI(
        time_to_validation_days_median=_percentile(ttv, 0.5),
        time_to_validation_days_p90=_percentile(ttv, 0.9),
        cases_with_validation=len(ttv),
        li_to_ll_conversion_pct=round(li_to_ll, 1),
        cases_analysed_or_later=li_count,
        cases_validated_or_closed=ll_count,
        recurrence_rate_pct=round(recurrence_pct, 1),
        regressed_recommendations=regressed_recs,
        validated_recommendations=validated_recs,
        open_cases_by_opr=dict(opr_load),
        msr_narrow=round(msr_narrow, 4),
        msr_full=round(msr_full, 4),
        launched_count=launched,
        aborted_count=aborted,
        success_count=success,
        cost_per_effect_usd_by_type={k: round(v, 2) for k, v in cost_per_effect.items()},
        period_from=period_from,
        period_to=period_to,
    )
