"""A fix that keeps failing is a wrong diagnosis, not a slow success (ADR-027).

`evidence_count` was incremented on every regression, written into the audit
payload — and never read by anything. A recommendation could cycle
DONE → regress → IN_PROGRESS → DONE → regress indefinitely while the counter
climbed in a column nobody looks at. The loop had no exit and no escalation.

Borrowed from the parallel team's principle 10: after N iterations the system
hands the decision to a person with an explicit message instead of quietly
recomputing forever.
"""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.models.aar import (
    AARCase,
    Recommendation,
    RecommendationStatus,
    TriggerType,
)
from aar_api.models.audit import AuditAction, AuditLog
from aar_api.services.recommendation_validation import (
    ValidationConfig,
    auto_validate_recommendations,
)

_Session = async_sessionmaker(_engine, expire_on_commit=False)
SIG = "T2:loss:c"


async def _recommendation(evidence_count: int) -> int:
    async with _Session() as s:
        case = AARCase(title="Кейс", trigger=TriggerType.REPEATED_REASON)
        s.add(case)
        await s.flush()
        rec = Recommendation(
            case_id=case.id,
            text="Провести інструктаж",
            status=RecommendationStatus.DONE,
            signature=SIG,
            evidence_count=evidence_count,
            validated_at=datetime.now(UTC) - timedelta(days=30),
        )
        s.add(rec)
        await s.flush()
        rid = rec.id
        await s.commit()
    return rid


async def _run(rid: int) -> tuple[list[int], list[int], list[int]]:
    async with _Session() as s:
        result = await auto_validate_recommendations(
            s, date.today(), {f"{SIG}:{date.today().isoformat()}"}, ValidationConfig()
        )
        await s.commit()
    return result


async def _escalations() -> list[AuditLog]:
    async with _Session() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.action == AuditAction.RECOMMENDATION_ESCALATED
                    )
                )
            ).scalars()
        )


async def test_a_first_setback_is_just_a_regression() -> None:
    rid = await _recommendation(evidence_count=0)
    _auto, regressed, escalated = await _run(rid)

    assert regressed == [rid]
    assert escalated == []
    assert await _escalations() == []


async def test_the_third_failure_is_escalated_to_a_person() -> None:
    """Two is a setback; three is a wrong diagnosis."""
    rid = await _recommendation(evidence_count=2)
    _auto, regressed, escalated = await _run(rid)

    assert regressed == [rid]
    assert escalated == [rid]

    entries = await _escalations()
    assert len(entries) == 1
    assert entries[0].entity_id == str(rid)
    assert entries[0].payload["evidence_count"] == 3
    assert entries[0].payload["reason"] == "regressed_repeatedly"


async def test_the_chain_shows_when_the_loop_stopped_being_routine() -> None:
    """Every regression entry carries the flag, not only the escalating one."""
    rid = await _recommendation(evidence_count=2)
    await _run(rid)

    async with _Session() as s:
        regressions = list(
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.action == AuditAction.RECOMMENDATION_REGRESSED
                    )
                )
            ).scalars()
        )
    assert len(regressions) == 1
    assert regressions[0].payload["escalated"] is True


async def test_escalation_does_not_stop_the_recommendation_being_worked() -> None:
    """Escalating is a message to a person, not a status the engine invents.

    The recommendation goes back to IN_PROGRESS exactly as before; what
    changed is that the repeated failure is now visible.
    """
    rid = await _recommendation(evidence_count=2)
    await _run(rid)

    async with _Session() as s:
        rec = await s.get(Recommendation, rid)
    assert rec is not None
    assert rec.status == RecommendationStatus.IN_PROGRESS
    assert rec.evidence_count == 3


async def test_the_threshold_is_configurable_not_a_belief() -> None:
    rid = await _recommendation(evidence_count=0)
    async with _Session() as s:
        _auto, _reg, escalated = await auto_validate_recommendations(
            s,
            date.today(),
            {f"{SIG}:{date.today().isoformat()}"},
            ValidationConfig(max_regressions=1),
        )
        await s.commit()
    assert escalated == [rid]
