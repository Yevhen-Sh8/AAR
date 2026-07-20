"""Mission Prep Brief (Wave 7) — AAR як ВХІД у планування.

Реалізує пункт 3 стратегії постачання (docs/concept/positioning.md §5):
планувальник задає профіль завдання (ключові слова / тип виробу /
експлуатант) → система збирає в один пакет усе, що організація вже знає
про такий профіль:

  1. активні проактивні сигнали (Wave 6) — попередження/ризики ДО вильоту;
  2. валідовані уроки з бази досвіду (CAL, тільки validated — ADR-009);
  3. уроки з завершених AAR-кейсів (lesson_identified);
  4. відкриті рекомендації, що ще не впроваджені;
  5. об'єктивна статистика виробів за профілем (MSR, топ-причини втрат).

Релевантність — детермінований підрахунок збігів токенів запиту в
title/description (без LLM: брифінг має працювати миттєво й офлайн;
LLM-синтез можна додати поверх окремим викликом).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.models.aar import AARCase, CaseStatus, Recommendation, RecommendationStatus
from aar_api.models.context import AssetStatus, ContextAsset
from aar_api.models.dictionaries import ItemType, LossReason, Operator
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.models.signal import PreTaskSignal, SignalStatus

_TOKEN_RE = re.compile(r"[\wа-яіїєґА-ЯІЇЄҐ]{3,}", re.UNICODE)


def _tokens(query: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(query or "")]


def _score(tokens: list[str], *texts: str | None) -> int:
    """Number of query tokens that occur in any of the given texts."""
    haystack = " ".join(t for t in texts if t).lower()
    return sum(1 for tok in tokens if tok in haystack)


@dataclass
class ProfileStats:
    window_days: int
    launched: int = 0
    success: int = 0
    lost: int = 0
    repaired: int = 0
    aborted: int = 0
    msr: float = 0.0
    top_loss_reasons: list[str] = field(default_factory=list)


@dataclass
class BriefItem:
    id: int
    title: str
    detail: str | None
    meta: str
    relevance: int


@dataclass
class MissionBrief:
    query: str
    item_type_code: str | None
    operator_code: str | None
    stats: ProfileStats
    signals: list[BriefItem]
    validated_lessons: list[BriefItem]
    case_lessons: list[BriefItem]
    open_recommendations: list[BriefItem]


async def compute_mission_brief(
    session: AsyncSession,
    *,
    query: str = "",
    item_type_code: str | None = None,
    operator_code: str | None = None,
    window_days: int = 90,
    today: date | None = None,
    limit_per_section: int = 10,
) -> MissionBrief:
    tokens = _tokens(query)
    today = today or date.today()
    since = today - timedelta(days=window_days)

    def rank(items: list[BriefItem]) -> list[BriefItem]:
        # With a query: relevance first (drop zero-hits), newest as tiebreak.
        # Without a query: just newest first — everything is "relevant".
        if tokens:
            items = [i for i in items if i.relevance > 0]
        items.sort(key=lambda i: (-i.relevance, -i.id))
        return items[:limit_per_section]

    # ── 1. Активні сигнали (до завдання) ──────────────────────────────────
    signal_rows = list(
        await session.scalars(
            select(PreTaskSignal).where(
                PreTaskSignal.status.in_(
                    [SignalStatus.NEW, SignalStatus.ACKNOWLEDGED, SignalStatus.ACCEPTED]
                )
            )
        )
    )
    signals = rank([
        BriefItem(
            id=s.id,
            title=s.title,
            detail=s.description,
            meta=f"{s.kind.value} · {s.status.value}"
            + (f" · {s.task_context}" if s.task_context else ""),
            relevance=_score(tokens, s.title, s.description, s.task_context),
        )
        for s in signal_rows
    ])

    # ── 2. Валідовані уроки з бази досвіду (ADR-009: тільки validated) ────
    asset_rows = list(
        await session.scalars(
            select(ContextAsset).where(ContextAsset.status == AssetStatus.VALIDATED)
        )
    )
    validated_lessons = rank([
        BriefItem(
            id=a.id,
            title=a.title,
            detail=a.description,
            meta=f"{a.type.value}"
            + (f" · conf={a.confidence:.2f}" if a.confidence is not None else ""),
            relevance=_score(tokens, a.title, a.description),
        )
        for a in asset_rows
    ])

    # ── 3. Уроки з кейсів, що пройшли валідацію циклу ─────────────────────
    case_rows = list(
        await session.scalars(
            select(AARCase).where(
                AARCase.lesson_identified.is_not(None),
                AARCase.status.in_([CaseStatus.VALIDATED, CaseStatus.CLOSED]),
            )
        )
    )
    case_lessons = rank([
        BriefItem(
            id=c.id,
            title=c.lesson_identified or c.title,
            detail=c.analysis,
            meta=f"кейс #{c.id} · {c.status.value}" + (f" · OPR: {c.opr}" if c.opr else ""),
            relevance=_score(
                tokens, c.title, c.lesson_identified, c.analysis, c.what_happened
            ),
        )
        for c in case_rows
    ])

    # ── 4. Відкриті рекомендації (ще не впроваджені) ──────────────────────
    rec_rows = list(
        await session.execute(
            select(Recommendation, AARCase)
            .join(AARCase, AARCase.id == Recommendation.case_id)
            .where(
                Recommendation.status.in_(
                    [RecommendationStatus.PROPOSED, RecommendationStatus.IN_PROGRESS]
                )
            )
        )
    )
    open_recommendations = rank([
        BriefItem(
            id=rec.id,
            title=rec.text,
            detail=None,
            meta=f"кейс #{case.id} · {rec.status.value}"
            + (f" · OPR: {case.opr}" if case.opr else ""),
            relevance=_score(tokens, rec.text, case.title, case.lesson_identified),
        )
        for rec, case in rec_rows
    ])

    # ── 5. Об'єктивна статистика за профілем ──────────────────────────────
    ev_stmt = (
        select(UsageEvent, LossReason.code)
        .join(Item, Item.id == UsageEvent.item_id)
        .join(ItemType, ItemType.id == Item.item_type_id)
        .join(Operator, Operator.id == UsageEvent.operator_id)
        .join(LossReason, LossReason.id == UsageEvent.loss_reason_id, isouter=True)
        .where(UsageEvent.event_date >= since)
    )
    if item_type_code:
        ev_stmt = ev_stmt.where(ItemType.code == item_type_code)
    if operator_code:
        ev_stmt = ev_stmt.where(Operator.code == operator_code)
    ev_rows = list(await session.execute(ev_stmt))

    stats = ProfileStats(window_days=window_days)
    loss_counter: dict[str, int] = {}
    for ev, loss_code in ev_rows:
        if ev.aborted:
            stats.aborted += 1
            continue
        stats.launched += 1
        if ev.outcome == Outcome.SUCCESS:
            stats.success += 1
        elif ev.outcome == Outcome.LOST:
            stats.lost += 1
            if loss_code:
                loss_counter[loss_code] = loss_counter.get(loss_code, 0) + 1
        elif ev.outcome == Outcome.REPAIR:
            stats.repaired += 1
    stats.msr = round(stats.success / stats.launched, 4) if stats.launched else 0.0
    stats.top_loss_reasons = [
        f"{code} (×{n})"
        for code, n in sorted(loss_counter.items(), key=lambda kv: -kv[1])[:3]
    ]

    return MissionBrief(
        query=query,
        item_type_code=item_type_code,
        operator_code=operator_code,
        stats=stats,
        signals=signals,
        validated_lessons=validated_lessons,
        case_lessons=case_lessons,
        open_recommendations=open_recommendations,
    )
