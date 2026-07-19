"""Wave 6 — pre-task proactive signals.

Endpoints implementing the "Проактивна взаємодія" concept
(docs/concept/positioning.md): warnings, risks, proposals and info notes
submitted BEFORE task execution, reviewed by responsible persons, and — when
they deserve structured follow-up — escalated into full AAR cases.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.models.aar import AARCase, TriggerType
from aar_api.models.audit import AuditAction
from aar_api.models.integration import WebhookEventKind
from aar_api.models.signal import PreTaskSignal, SignalKind, SignalStatus
from aar_api.services.audit import append as audit_append
from aar_api.services.integrations import dispatch

router = APIRouter(prefix="/signals", tags=["signals"])

# Review transitions only move forward from NEW/ACKNOWLEDGED; terminal states
# (accepted / dismissed / converted) are final for this minimal lifecycle.
_REVIEWABLE = {SignalStatus.NEW, SignalStatus.ACKNOWLEDGED}


class SignalIn(BaseModel):
    kind: SignalKind
    title: str
    description: str | None = None
    author: str | None = None  # None = анонімно (TC 25-20 blame-free)
    task_context: str | None = None


class SignalReviewIn(BaseModel):
    status: SignalStatus
    review_note: str | None = None


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: SignalKind
    title: str
    description: str | None
    author: str | None
    task_context: str | None
    status: SignalStatus
    review_note: str | None
    case_id: int | None
    created_at: datetime
    reviewed_at: datetime | None


async def _get_signal(session: AsyncSession, signal_id: int) -> PreTaskSignal:
    signal = await session.get(PreTaskSignal, signal_id)
    if signal is None:
        raise HTTPException(404, "signal not found")
    return signal


@router.post("", response_model=SignalOut, status_code=201)
async def create_signal(
    payload: SignalIn, session: AsyncSession = Depends(get_session)
) -> PreTaskSignal:
    signal = PreTaskSignal(**payload.model_dump())
    session.add(signal)
    await session.flush()
    await audit_append(
        session,
        action=AuditAction.SIGNAL_CREATED,
        entity_type="pre_task_signal",
        entity_id=signal.id,
        payload={"kind": signal.kind.value, "title": signal.title},
    )
    try:
        await dispatch(
            session,
            WebhookEventKind.SIGNAL_CREATED,
            {
                "id": signal.id,
                "kind": signal.kind.value,
                "title": signal.title,
                "task_context": signal.task_context,
            },
        )
    except Exception:  # noqa: BLE001 — partner downtime must not block submission
        pass
    await session.commit()
    await session.refresh(signal)
    return signal


@router.get("", response_model=list[SignalOut])
async def list_signals(
    status: SignalStatus | None = Query(default=None),
    kind: SignalKind | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[PreTaskSignal]:
    stmt = select(PreTaskSignal).order_by(PreTaskSignal.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(PreTaskSignal.status == status)
    if kind:
        stmt = stmt.where(PreTaskSignal.kind == kind)
    return list(await session.scalars(stmt))


@router.post("/{signal_id}/review", response_model=SignalOut)
async def review_signal(
    signal_id: int,
    payload: SignalReviewIn,
    session: AsyncSession = Depends(get_session),
) -> PreTaskSignal:
    """Move a signal through review: acknowledged / accepted / dismissed.

    Conversion to a case goes through /convert, not here.
    """
    if payload.status in (SignalStatus.NEW, SignalStatus.CONVERTED):
        raise HTTPException(422, f"cannot set status={payload.status.value} via review")
    signal = await _get_signal(session, signal_id)
    if signal.status not in _REVIEWABLE:
        raise HTTPException(
            409, f"signal already finalised (status={signal.status.value})"
        )
    signal.status = payload.status
    signal.review_note = payload.review_note
    signal.reviewed_at = datetime.now(UTC)
    await audit_append(
        session,
        action=AuditAction.SIGNAL_REVIEWED,
        entity_type="pre_task_signal",
        entity_id=signal.id,
        payload={"status": signal.status.value, "note": payload.review_note},
    )
    await session.commit()
    await session.refresh(signal)
    return signal


@router.post("/{signal_id}/convert", response_model=SignalOut)
async def convert_signal_to_case(
    signal_id: int, session: AsyncSession = Depends(get_session)
) -> PreTaskSignal:
    """Escalate a signal into a full AAR case.

    The case opens pre-filled from the signal (what_happened = signal text) so
    the NATO cycle picks up from the participant's original observation.
    """
    signal = await _get_signal(session, signal_id)
    if signal.status not in _REVIEWABLE:
        raise HTTPException(
            409, f"signal already finalised (status={signal.status.value})"
        )
    case = AARCase(
        title=f"Сигнал: {signal.title}",
        trigger=TriggerType.MANUAL,
        what_happened=signal.description or signal.title,
        summary=(
            f"Відкрито з проактивного сигналу #{signal.id} "
            f"({signal.kind.value})"
            + (f", контекст: {signal.task_context}" if signal.task_context else "")
        ),
    )
    session.add(case)
    await session.flush()
    signal.status = SignalStatus.CONVERTED
    signal.case_id = case.id
    signal.reviewed_at = datetime.now(UTC)
    await audit_append(
        session,
        action=AuditAction.SIGNAL_CONVERTED,
        entity_type="pre_task_signal",
        entity_id=signal.id,
        payload={"case_id": case.id},
    )
    await session.commit()
    await session.refresh(signal)
    return signal
