"""Tests for Wave 2 — learning-loop meta-KPIs."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import (
    AARCase,
    CaseStatus,
    Recommendation,
    RecommendationStatus,
    TriggerType,
)
from aar_api.models.dictionaries import ItemType, Operator
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.services.learning_metrics import compute_loop_kpi


async def test_loop_kpi_endpoint_returns_full_shape() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="A", unit_cost_usd=Decimal("500.00"))
        op = Operator(code="E-01", name_uk="01")
        s.add_all([a, op])
        await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/learning/loop-kpi")
        assert r.status_code == 200
        body = r.json()
        for key in [
            "time_to_validation_days_median",
            "li_to_ll_conversion_pct",
            "recurrence_rate_pct",
            "open_cases_by_opr",
            "msr_narrow",
            "msr_full",
            "cost_per_effect_usd_by_type",
        ]:
            assert key in body


async def test_time_to_validation_median_computed_from_validated_at() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with Session() as s:
        for days in (3, 7, 14):
            c = AARCase(
                title=f"c{days}",
                trigger=TriggerType.MANUAL,
                status=CaseStatus.VALIDATED,
            )
            s.add(c)
            await s.flush()
            c.opened_at = now - timedelta(days=days + 1)
            c.validated_at = now - timedelta(days=1)
        await s.commit()
    async with Session() as s:
        kpi = await compute_loop_kpi(s)
        # Three deltas: 3, 7, 14 → median = 7
        assert kpi.cases_with_validation == 3
        assert kpi.time_to_validation_days_median is not None
        assert 6.5 < kpi.time_to_validation_days_median < 7.5


async def test_li_to_ll_conversion_pct() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        # 4 analysed, 1 endorsed, 1 validated, 1 closed → analysed-or-later=7
        # 2 reached LL → 2/7 ≈ 28.6%
        for status in [
            CaseStatus.ANALYSED, CaseStatus.ANALYSED, CaseStatus.ANALYSED,
            CaseStatus.ANALYSED, CaseStatus.ENDORSED,
            CaseStatus.VALIDATED, CaseStatus.CLOSED,
        ]:
            s.add(AARCase(title="x", trigger=TriggerType.MANUAL, status=status))
        # An OPEN case — does NOT count for either numerator or denominator
        s.add(AARCase(title="open", trigger=TriggerType.MANUAL, status=CaseStatus.OPEN))
        await s.commit()
    async with Session() as s:
        kpi = await compute_loop_kpi(s)
        assert kpi.cases_analysed_or_later == 7
        assert kpi.cases_validated_or_closed == 2
        assert 28.0 <= kpi.li_to_ll_conversion_pct <= 29.0


async def test_recurrence_rate_uses_regressed_at() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        c = AARCase(title="c", trigger=TriggerType.MANUAL)
        s.add(c)
        await s.flush()
        # 3 validated, 1 regressed → 1/3 = 33.3%
        for i in range(3):
            s.add(Recommendation(
                case_id=c.id, text=f"r{i}",
                status=RecommendationStatus.VALIDATED,
                validated_at=datetime.now(UTC),
            ))
        s.add(Recommendation(
            case_id=c.id, text="regressed",
            status=RecommendationStatus.IN_PROGRESS,
            validated_at=datetime.now(UTC),
            regressed_at=datetime.now(UTC),
        ))
        await s.commit()
    async with Session() as s:
        kpi = await compute_loop_kpi(s)
        assert kpi.validated_recommendations == 3
        assert kpi.regressed_recommendations == 1
        assert 33.0 <= kpi.recurrence_rate_pct <= 34.0


async def test_msr_narrow_vs_full_with_aborts() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    today = date.today()
    async with Session() as s:
        a = ItemType(code="A", name_uk="A")
        op = Operator(code="E-01", name_uk="01")
        s.add_all([a, op])
        await s.flush()
        items = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(10)]
        s.add_all(items)
        await s.flush()
        # 6 launched (4 success, 2 lost), 4 aborted (РЕБ before launch)
        # MSR_narrow = 4/6 = 0.6667
        # MSR_full   = 4/10 = 0.40
        s.add_all([
            UsageEvent(item_id=items[i].id, operator_id=op.id,
                       event_date=today, outcome=Outcome.SUCCESS)
            for i in range(4)
        ])
        s.add_all([
            UsageEvent(item_id=items[i].id, operator_id=op.id,
                       event_date=today, outcome=Outcome.LOST,
                       aborted=False)
            for i in (4, 5)
        ])
        s.add_all([
            UsageEvent(item_id=items[i].id, operator_id=op.id,
                       event_date=today, outcome=Outcome.SUCCESS,
                       aborted=True, abort_reason="ew_jam")
            for i in (6, 7, 8, 9)
        ])
        await s.commit()
    async with Session() as s:
        kpi = await compute_loop_kpi(s)
        assert kpi.launched_count == 6
        assert kpi.aborted_count == 4
        assert kpi.success_count == 4
        assert 0.66 < kpi.msr_narrow < 0.67
        assert 0.39 < kpi.msr_full < 0.41


async def test_cost_per_effect_uses_unit_cost() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    today = date.today()
    async with Session() as s:
        a = ItemType(code="A", name_uk="A", unit_cost_usd=Decimal("1000.00"))
        op = Operator(code="E-01", name_uk="01")
        s.add_all([a, op])
        await s.flush()
        items = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(5)]
        s.add_all(items)
        await s.flush()
        # 5 launches × $1000 = $5000; 2 successes → $2500 per effect
        s.add_all([
            UsageEvent(item_id=items[0].id, operator_id=op.id,
                       event_date=today, outcome=Outcome.SUCCESS),
            UsageEvent(item_id=items[1].id, operator_id=op.id,
                       event_date=today, outcome=Outcome.SUCCESS),
            UsageEvent(item_id=items[2].id, operator_id=op.id,
                       event_date=today, outcome=Outcome.LOST),
            UsageEvent(item_id=items[3].id, operator_id=op.id,
                       event_date=today, outcome=Outcome.LOST),
            UsageEvent(item_id=items[4].id, operator_id=op.id,
                       event_date=today, outcome=Outcome.REPAIR),
        ])
        await s.commit()
    async with Session() as s:
        kpi = await compute_loop_kpi(s)
        assert "A" in kpi.cost_per_effect_usd_by_type
        assert abs(kpi.cost_per_effect_usd_by_type["A"] - 2500.0) < 0.01


async def test_open_cases_by_opr_groups_correctly() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            AARCase(title="c1", trigger=TriggerType.MANUAL,
                    opr="Технічна служба", status=CaseStatus.ANALYSED),
            AARCase(title="c2", trigger=TriggerType.MANUAL,
                    opr="Технічна служба", status=CaseStatus.ENDORSED),
            AARCase(title="c3", trigger=TriggerType.MANUAL,
                    opr="Оперативний відділ", status=CaseStatus.OPEN),
            # Closed → not in load
            AARCase(title="c4", trigger=TriggerType.MANUAL,
                    opr="Технічна служба", status=CaseStatus.CLOSED),
            # No OPR → bucketed as "не призначено"
            AARCase(title="c5", trigger=TriggerType.MANUAL, status=CaseStatus.OPEN),
        ])
        await s.commit()
    async with Session() as s:
        kpi = await compute_loop_kpi(s)
        assert kpi.open_cases_by_opr.get("Технічна служба") == 2
        assert kpi.open_cases_by_opr.get("Оперативний відділ") == 1
        assert kpi.open_cases_by_opr.get("не призначено") == 1
