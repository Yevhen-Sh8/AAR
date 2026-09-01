"""Wave 13 (ADR-026) — is the remedial answer formulaic?

The Parallax concept was «anti-predictability», with a mechanism we refused:
requiring every recommendation to carry ≥2 equivalent variants. That forces an
invented second option wherever the evidence supports one course of action, and
manufacturing content is the failure this project has spent its life removing.

What is honestly measurable is the repetition itself — a fact in the data, not
an inference about what an adversary can read.
"""
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase, Recommendation, TriggerType
from aar_api.models.dictionaries import Operator
from aar_api.services.response_diversity import normalise

_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def _operator(code: str = "E-01") -> int:
    async with _Session() as s:
        op = Operator(code=code, name_uk=code)
        s.add(op)
        await s.flush()
        oid = op.id
        await s.commit()
    return oid


async def _case_with_recs(
    operator_id: int | None,
    trigger: TriggerType,
    texts: list[str],
    opened_at: datetime | None = None,
) -> None:
    async with _Session() as s:
        c = AARCase(
            title="Кейс",
            trigger=trigger,
            operator_id=operator_id,
            opened_at=opened_at or datetime.now(UTC),
        )
        s.add(c)
        await s.flush()
        for t in texts:
            s.add(Recommendation(case_id=c.id, text=t))
        await s.commit()


async def _get(**params) -> list[dict]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/learning/response-diversity", params=params)
        assert r.status_code == 200, r.text
        return list(r.json())


async def test_one_action_repeated_for_one_trigger_is_reported() -> None:
    op = await _operator()
    for _ in range(4):
        await _case_with_recs(op, TriggerType.MSR_DROP, ["Провести додатковий інструктаж"])

    rows = await _get()
    assert len(rows) == 1
    p = rows[0]
    assert p["operator_code"] == "E-01"
    assert p["trigger"] == "msr_drop"
    assert p["cases"] == 4
    assert p["distinct_responses"] == 1
    assert p["dominant_count"] == 4
    assert p["dominant_share"] == 1.0
    # The wording a person actually wrote, not the folded form.
    assert p["dominant_text"] == "Провести додатковий інструктаж"


async def test_a_varied_response_is_not_reported() -> None:
    """Four different answers to the same trigger is the healthy case."""
    op = await _operator()
    for i in range(4):
        await _case_with_recs(op, TriggerType.MSR_DROP, [f"Дія варіант {i}"])
    assert await _get() == []


async def test_twice_is_a_coincidence_not_a_habit() -> None:
    op = await _operator()
    for _ in range(2):
        await _case_with_recs(op, TriggerType.MSR_DROP, ["Та сама дія"])
    assert await _get() == []
    # …and the threshold is a parameter, not a belief.
    assert len(await _get(min_cases=2)) == 1


async def test_trivial_wording_differences_do_not_hide_the_repetition() -> None:
    op = await _operator()
    for text in [
        "Провести інструктаж.",
        "провести  інструктаж",
        "Провести інструктаж!",
    ]:
        await _case_with_recs(op, TriggerType.REPEATED_REASON, [text])

    rows = await _get()
    assert len(rows) == 1
    assert rows[0]["distinct_responses"] == 1
    assert rows[0]["dominant_count"] == 3


async def test_normalisation_stays_shallow() -> None:
    """Two genuinely different actions must never fold into one finding."""
    assert normalise("Провести інструктаж.") == normalise("провести  інструктаж")
    assert normalise("Замінити антену") != normalise("Замінити акумулятор")


async def test_each_operator_and_trigger_is_judged_on_its_own() -> None:
    a = await _operator("E-01")
    b = await _operator("E-02")
    for _ in range(3):
        await _case_with_recs(a, TriggerType.MSR_DROP, ["Дія A"])
    for _ in range(3):
        await _case_with_recs(b, TriggerType.MSR_DROP, ["Дія A"])
    # Same operator, DIFFERENT trigger — a separate pattern, not a merge.
    for _ in range(3):
        await _case_with_recs(a, TriggerType.ITEM_ANOMALY, ["Дія B"])

    rows = await _get()
    keys = {(r["operator_code"], r["trigger"]) for r in rows}
    assert keys == {
        ("E-01", "msr_drop"),
        ("E-02", "msr_drop"),
        ("E-01", "item_anomaly"),
    }


async def test_a_dominant_action_beside_an_occasional_one_still_counts() -> None:
    """80% of the answers landing on one action is already a habit."""
    op = await _operator()
    for _ in range(5):
        await _case_with_recs(op, TriggerType.MSR_DROP, ["Стандартна дія"])
    await _case_with_recs(op, TriggerType.MSR_DROP, ["Інша дія"])

    rows = await _get()
    assert len(rows) == 1
    assert rows[0]["distinct_responses"] == 2
    assert rows[0]["dominant_count"] == 5
    assert rows[0]["dominant_share"] == round(5 / 6, 3)


async def test_the_window_is_respected() -> None:
    op = await _operator()
    old = datetime.now(UTC) - timedelta(days=500)
    for _ in range(4):
        await _case_with_recs(op, TriggerType.MSR_DROP, ["Стара дія"], opened_at=old)
    assert await _get() == []
