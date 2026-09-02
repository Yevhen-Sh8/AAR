"""Auto-trigger engine for AAR cases (T1..T4).

T1: operator η_c (MSR_c) below threshold for N consecutive days
T2: same loss/repair reason repeated K+ times within a window
T3: anomaly on a single serial number (M+ repairs/losses within a window)
T4: enterprise-wide η (MSR) dropped by more than P percentage points day-over-day
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from aar_api.models.aar import AARCase, TriggerType
from aar_api.models.audit import AuditAction
from aar_api.models.dictionaries import LossReason, Operator, RepairReason, Zone
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.services.audit import append as audit_append
from aar_api.services.recommendation_validation import (
    ValidationConfig,
    auto_validate_recommendations,
)


@dataclass(frozen=True)
class TriggerConfig:
    t1_msr_c_threshold: float = 0.70
    t1_consecutive_days: int = 3
    t2_repeat_count: int = 3
    t2_window_days: int = 7
    t3_anomaly_count: int = 2
    t3_window_days: int = 30
    t4_drop_pp: float = 10.0


async def _events_in_range(
    session: AsyncSession, start: date, end: date
) -> list:
    LR = aliased(LossReason)
    RR = aliased(RepairReason)
    stmt = (
        select(
            UsageEvent.id,
            UsageEvent.event_date,
            UsageEvent.outcome,
            UsageEvent.operator_id,
            UsageEvent.item_id,
            Item.serial_no,
            Operator.code.label("operator_code"),
            LR.code.label("loss_code"),
            LR.zone.label("loss_zone"),
            RR.code.label("repair_code"),
            RR.zone.label("repair_zone"),
        )
        .join(Operator, Operator.id == UsageEvent.operator_id)
        .join(Item, Item.id == UsageEvent.item_id)
        .join(LR, LR.id == UsageEvent.loss_reason_id, isouter=True)
        .join(RR, RR.id == UsageEvent.repair_reason_id, isouter=True)
        .where(UsageEvent.event_date.between(start, end))
    )
    return list(await session.execute(stmt))


def _msr_c(events: list) -> float | None:
    launched = len(events)
    if not launched:
        return None
    success = sum(1 for e in events if e.outcome == Outcome.SUCCESS)
    not_operator = sum(
        1 for e in events
        if e.outcome == Outcome.LOST and e.loss_zone in (Zone.EXTERNAL, Zone.MANUFACTURER)
    )
    cleaned = launched - not_operator
    return (success / cleaned) if cleaned else 0.0


def _eval_t1(events: list, cfg: TriggerConfig, today: date) -> list[tuple[str, int]]:
    by_op_day: dict[tuple[str, int, date], list] = defaultdict(list)
    for e in events:
        by_op_day[(e.operator_code, e.operator_id, e.event_date)].append(e)
    out: list[tuple[str, int]] = []
    operators = {(op, op_id) for (op, op_id, _) in by_op_day}
    for op_code, op_id in operators:
        days = [today - timedelta(days=i) for i in range(cfg.t1_consecutive_days)]
        msr_values = [_msr_c(by_op_day.get((op_code, op_id, d), [])) for d in days]
        if all(k is not None and k < cfg.t1_msr_c_threshold for k in msr_values):
            out.append((op_code, op_id))
    return out


def _eval_t2(events: list, cfg: TriggerConfig, today: date) -> list[str]:
    start = today - timedelta(days=cfg.t2_window_days - 1)
    counter: dict[tuple[str, str], int] = defaultdict(int)
    for e in events:
        if e.event_date < start:
            continue
        if e.outcome == Outcome.LOST and e.loss_code:
            counter[("loss", e.loss_code)] += 1
        elif e.outcome == Outcome.REPAIR and e.repair_code:
            counter[("repair", e.repair_code)] += 1
    return [f"{kind}:{code}" for (kind, code), n in counter.items() if n >= cfg.t2_repeat_count]


def _eval_t3(events: list, cfg: TriggerConfig, today: date) -> list[tuple[str, int]]:
    start = today - timedelta(days=cfg.t3_window_days - 1)
    by_item: dict[tuple[str, int], int] = defaultdict(int)
    for e in events:
        if e.event_date < start:
            continue
        if e.outcome in (Outcome.LOST, Outcome.REPAIR):
            by_item[(e.serial_no, e.item_id)] += 1
    return [(serial, item_id) for (serial, item_id), n in by_item.items()
            if n >= cfg.t3_anomaly_count]


def _eval_t4(events: list, cfg: TriggerConfig, today: date) -> bool:
    yest = today - timedelta(days=1)
    today_events = [e for e in events if e.event_date == today]
    yest_events = [e for e in events if e.event_date == yest]
    if not today_events or not yest_events:
        return False
    today_msr = sum(1 for e in today_events if e.outcome == Outcome.SUCCESS) / len(today_events)
    yest_msr = sum(1 for e in yest_events if e.outcome == Outcome.SUCCESS) / len(yest_events)
    return (yest_msr - today_msr) * 100 > cfg.t4_drop_pp


async def _signature_exists(session: AsyncSession, signature: str) -> bool:
    row = await session.scalar(
        select(AARCase).where(AARCase.title.like(f"%[{signature}]%"))
    )
    return row is not None


async def evaluate_triggers(
    session: AsyncSession, today: date, cfg: TriggerConfig | None = None
) -> tuple[list[AARCase], int, list[int], list[int]]:
    """Run trigger engine + Monitor & Validate stage.

    Returns: (created_cases, skipped_count, auto_validated_rec_ids, regressed_rec_ids)
    """
    cfg = cfg or TriggerConfig()
    window_start = today - timedelta(days=max(
        cfg.t1_consecutive_days, cfg.t2_window_days, cfg.t3_window_days, 2
    ) - 1)
    events = await _events_in_range(session, window_start, today)

    created: list[AARCase] = []
    skipped = 0
    fired_signatures: set[str] = set()

    for op_code, op_id in _eval_t1(events, cfg, today):
        sig = f"T1:{op_code}:{today.isoformat()}"
        fired_signatures.add(sig)
        if await _signature_exists(session, sig):
            skipped += 1
            continue
        case = AARCase(
            title=f"Зниження MSR_c у {op_code} [{sig}]",
            trigger=TriggerType.MSR_DROP,
            operator_id=op_id,
        )
        session.add(case)
        created.append(case)

    for sig_tail in _eval_t2(events, cfg, today):
        sig = f"T2:{sig_tail}:{today.isoformat()}"
        fired_signatures.add(sig)
        if await _signature_exists(session, sig):
            skipped += 1
            continue
        case = AARCase(
            title=f"Повторювана причина {sig_tail} [{sig}]",
            trigger=TriggerType.REPEATED_REASON,
        )
        session.add(case)
        created.append(case)

    for serial, _item_id in _eval_t3(events, cfg, today):
        sig = f"T3:{serial}:{today.isoformat()}"
        fired_signatures.add(sig)
        if await _signature_exists(session, sig):
            skipped += 1
            continue
        case = AARCase(
            title=f"Аномалія виробу {serial} [{sig}]",
            trigger=TriggerType.ITEM_ANOMALY,
        )
        session.add(case)
        created.append(case)

    if _eval_t4(events, cfg, today):
        sig = f"T4:{today.isoformat()}"
        fired_signatures.add(sig)
        if await _signature_exists(session, sig):
            skipped += 1
        else:
            case = AARCase(
                title=f"Падіння MSR підприємства > {cfg.t4_drop_pp} в.п. [{sig}]",
                trigger=TriggerType.ENTERPRISE_DROP,
            )
            session.add(case)
            created.append(case)

    await session.flush()

    # Case-open is a critical auditable action, but only the MANUAL path
    # (routers/aar.create_case) recorded it — so in production, where triggers
    # open most cases, the majority of case-opens were absent from the chain.
    # Appended after the flush so every case already has its id.
    for case in created:
        await audit_append(
            session,
            action=AuditAction.CASE_CREATED,
            entity_type="aar_case",
            entity_id=case.id,
            payload={
                "title": case.title,
                "trigger": case.trigger.value,
                "operator_id": case.operator_id,
                "auto": True,
            },
        )

    # Monitor & Validate — close the NATO LL loop.
    # `escalated` is a subset of `regressed`; each one already wrote its own
    # RECOMMENDATION_ESCALATED entry to the chain, so it needs no summary row.
    auto_validated, regressed, _escalated = await auto_validate_recommendations(
        session, today, fired_signatures, ValidationConfig()
    )
    return created, skipped, auto_validated, regressed
