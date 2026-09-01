"""Wave 13 (ADR-024) — the decision, judged apart from how it turned out.

The zone model already draws this line at Level 1: a loss with zone=external
does not count against the crew, which is the whole reason η_c exists. Level 2
had no equivalent — a case recorded what happened and never said whether the
decision behind it was defensible on what was knowable at the time.

The cell nobody records is a flawed decision with a good outcome: it got away
with it, no trigger fires, and the unit institutionalises a bad practice
because the result looked fine.
"""
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase, CaseStatus, DecisionQuality, TriggerType

_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def _case(**fields) -> int:
    async with _Session() as s:
        c = AARCase(title=fields.pop("title", "Кейс"), **fields)
        s.add(c)
        await s.flush()
        cid = c.id
        await s.commit()
    return cid


async def test_a_new_case_starts_unassessed() -> None:
    """Never guessed. An unjudged decision must not read as an approved one."""
    cid = await _case(trigger=TriggerType.MANUAL)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        body = (await c.get(f"/aar/cases/{cid}")).json()
    assert body["decision_quality"] == "unassessed"
    assert body["decision_rationale"] is None


async def test_the_assessment_is_recorded_with_what_was_known() -> None:
    cid = await _case(trigger=TriggerType.MSR_DROP)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.patch(
            f"/aar/cases/{cid}",
            json={
                "decision_quality": "sound",
                "decision_rationale": "На момент вильоту РЕБ у секторі не фіксували.",
            },
        )
        assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision_quality"] == "sound"
    assert "РЕБ" in body["decision_rationale"]


async def test_a_bad_outcome_can_carry_a_sound_decision() -> None:
    """The point of the whole field: the two axes are independent.

    A case opened by a metric drop (bad outcome by construction) can still be
    judged a sound call. Without this the unit learns to fear luck.
    """
    cid = await _case(trigger=TriggerType.MSR_DROP, status=CaseStatus.ANALYSED)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.patch(f"/aar/cases/{cid}", json={"decision_quality": "sound"})
        kpi = (await c.get("/learning/loop-kpi")).json()
    assert kpi["decision_quality_counts"]["sound"] == 1
    assert kpi["decision_quality_counts"]["unassessed"] == 0


async def test_remedial_action_tasked_without_judging_the_decision_is_counted() -> None:
    """Endorsing means tasking an OPR with a fix. Doing that before deciding
    whether the decision or the circumstances were at fault is how a unit
    trains against bad luck."""
    await _case(trigger=TriggerType.MSR_DROP, status=CaseStatus.ENDORSED)
    await _case(trigger=TriggerType.MSR_DROP, status=CaseStatus.IMPLEMENTED)
    # Assessed → not counted.
    await _case(
        trigger=TriggerType.MSR_DROP,
        status=CaseStatus.VALIDATED,
        decision_quality=DecisionQuality.FLAWED,
    )
    # Not yet endorsed → not counted either.
    await _case(trigger=TriggerType.MSR_DROP, status=CaseStatus.OPEN)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        kpi = (await c.get("/learning/loop-kpi")).json()
    assert kpi["endorsed_without_assessment"] == 2


async def test_a_bad_call_that_worked_out_is_surfaced() -> None:
    """A trigger only fires on a bad number, so a MANUAL case with a flawed
    decision is one a human opened on a run that looked fine."""
    await _case(trigger=TriggerType.MANUAL, decision_quality=DecisionQuality.FLAWED)
    await _case(trigger=TriggerType.MANUAL, decision_quality=DecisionQuality.ACCEPTABLE)
    # Sound manual case — nothing was caught.
    await _case(trigger=TriggerType.MANUAL, decision_quality=DecisionQuality.SOUND)
    # Auto-opened flawed case — the metric already told us; not a near miss.
    await _case(trigger=TriggerType.MSR_DROP, decision_quality=DecisionQuality.FLAWED)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        kpi = (await c.get("/learning/loop-kpi")).json()
    assert kpi["caught_before_it_cost_anything"] == 2


async def test_the_breakdown_only_covers_the_requested_period() -> None:
    old = datetime.now(UTC) - timedelta(days=400)
    async with _Session() as s:
        c = AARCase(
            title="Старий",
            trigger=TriggerType.MANUAL,
            decision_quality=DecisionQuality.FLAWED,
            opened_at=old,
        )
        s.add(c)
        await s.commit()
    await _case(trigger=TriggerType.MANUAL, decision_quality=DecisionQuality.SOUND)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        kpi = (await c.get("/learning/loop-kpi")).json()
    assert kpi["decision_quality_counts"]["sound"] == 1
    assert kpi["decision_quality_counts"]["flawed"] == 0
