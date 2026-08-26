"""Tests for Wave 1: NATO LL cycle compliance.

Covers:
- Case state machine transitions (allowed vs forbidden moves).
- PATCH /aar/cases/{id} stores narrative fields.
- Auto-validation of recommendations on quiet window.
- Auto-regression on signature recurrence.
- Daily report conclusions block is generated.
"""
from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import (
    AARCase,
    Recommendation,
    RecommendationStatus,
    TriggerType,
)
from aar_api.models.dictionaries import ItemType, LossReason, Operator, Zone
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.services.recommendation_validation import (
    ValidationConfig,
    auto_validate_recommendations,
)

TODAY = date(2026, 6, 10)


async def test_state_machine_blocks_invalid_jump() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(AARCase(title="t", trigger=TriggerType.MANUAL))
        await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # open → validated is not allowed (must go via analysed/endorsed/implemented).
        r = await client.post(
            "/aar/cases/1/transition", json={"to": "validated"}
        )
        assert r.status_code == 409
        # open → analysed is allowed.
        r = await client.post(
            "/aar/cases/1/transition", json={"to": "analysed", "note": "проаналізовано"}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "analysed"
        # analysed → endorsed → implemented → validated → closed (full chain).
        for nxt in ("endorsed", "implemented", "validated", "closed"):
            r = await client.post("/aar/cases/1/transition", json={"to": nxt})
            assert r.status_code == 200, f"failed at {nxt}: {r.text}"
        assert r.json()["status"] == "closed"
        assert r.json()["closed_at"] is not None


async def test_patch_case_stores_nato_fields() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(AARCase(title="t", trigger=TriggerType.MANUAL))
        await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.patch(
            "/aar/cases/1",
            json={
                "what_was_planned": "запустити 10 виробів",
                "what_happened": "3 не повернулись",
                "analysis": "виявлено брак партії",
                "lesson_identified": "перевіряти партію перед видачою",
                "opr": "Технічна служба підприємства",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["analysis"] == "виявлено брак партії"
        assert body["lesson_identified"]
        assert body["opr"] == "Технічна служба підприємства"
        assert body["analysis_source"] == "manual"
        assert body["analysis_drafted_at"] is not None


async def test_auto_validation_after_quiet_window() -> None:
    """Recommendation marked DONE >14 days ago with no recurrence → auto-validated."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    long_ago = TODAY - timedelta(days=30)
    async with Session() as s:
        case = AARCase(title="x", trigger=TriggerType.REPEATED_REASON)
        s.add(case)
        await s.flush()
        rec = Recommendation(
            case_id=case.id,
            text="Довчити обслугу",
            status=RecommendationStatus.DONE,
            signature="T2:loss:c",
            validated_at=__import__("datetime").datetime.combine(
                long_ago, __import__("datetime").time.min
            ).replace(tzinfo=__import__("datetime").UTC),
        )
        s.add(rec)
        await s.commit()
        rec_id = rec.id

    async with Session() as s:
        auto_v, regressed = await auto_validate_recommendations(
            s, TODAY, recurring_signatures=set(), cfg=ValidationConfig()
        )
        await s.commit()
        assert rec_id in auto_v
        assert regressed == []
        refreshed = await s.get(Recommendation, rec_id)
        assert refreshed.status == RecommendationStatus.VALIDATED
        assert refreshed.auto_validated_at is not None


async def test_auto_regression_on_recurrence() -> None:
    """DONE recommendation whose signature fires again today → regressed."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        case = AARCase(title="x", trigger=TriggerType.REPEATED_REASON)
        s.add(case)
        await s.flush()
        rec = Recommendation(
            case_id=case.id,
            text="Замінити постачальника",
            status=RecommendationStatus.DONE,
            signature="T2:loss:c",
        )
        s.add(rec)
        await s.commit()
        rec_id = rec.id

    async with Session() as s:
        auto_v, regressed = await auto_validate_recommendations(
            s, TODAY,
            recurring_signatures={f"T2:loss:c:{TODAY.isoformat()}"},
            cfg=ValidationConfig(),
        )
        await s.commit()
        assert rec_id in regressed
        assert rec_id not in auto_v
        refreshed = await s.get(Recommendation, rec_id)
        assert refreshed.status == RecommendationStatus.IN_PROGRESS
        assert refreshed.regressed_at is not None
        assert refreshed.evidence_count == 1


async def test_daily_report_has_conclusions_block() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="A")
        e = Operator(code="E-01", name_uk="01")
        lr = LossReason(code="c", name_uk="c", zone=Zone.OPERATOR)
        s.add_all([a, e, lr])
        await s.flush()
        items = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(5)]
        s.add_all(items)
        await s.flush()
        s.add_all([
            UsageEvent(item_id=items[0].id, operator_id=e.id,
                       event_date=TODAY, outcome=Outcome.SUCCESS),
            UsageEvent(item_id=items[1].id, operator_id=e.id,
                       event_date=TODAY, outcome=Outcome.LOST,
                       loss_reason_id=lr.id),
            UsageEvent(item_id=items[2].id, operator_id=e.id,
                       event_date=TODAY, outcome=Outcome.LOST,
                       loss_reason_id=lr.id),
        ])
        await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/reports/daily", params={"date": TODAY.isoformat()})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "conclusions" in body
        c = body["conclusions"]
        assert c is not None
        assert any("c (×2)" in s for s in c["top_loss_reasons"])
        assert "Успішність" in c["headline"]
        assert "запущено 3" in c["headline"]
