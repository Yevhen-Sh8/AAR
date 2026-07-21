"""Wave 7 — Mission Prep Brief (docs/concept/positioning.md §5, пункт 3)."""
from datetime import date, timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase, CaseStatus, Recommendation, TriggerType
from aar_api.models.context import AssetStatus, ContextAsset, ContextAssetType
from aar_api.models.dictionaries import ItemType, LossReason, Operator, Zone
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.models.signal import PreTaskSignal, SignalKind, SignalStatus
from aar_api.services import llm as llm_service

TODAY = date.today()


async def _seed_world() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="A")
        b = ItemType(code="B", name_uk="B")
        op = Operator(code="E-01", name_uk="01")
        lr = LossReason(code="c", name_uk="c", zone=Zone.OPERATOR)
        s.add_all([a, b, op, lr])
        await s.flush()

        items_a = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(6)]
        item_b = Item(serial_no="B-00001", item_type_id=b.id)
        s.add_all([*items_a, item_b])
        await s.flush()

        # Type A: 3 success, 2 lost(c), 1 aborted → launched=5, msr=0.6
        for i in range(3):
            s.add(UsageEvent(item_id=items_a[i].id, operator_id=op.id,
                             event_date=TODAY, outcome=Outcome.SUCCESS))
        for i in (3, 4):
            s.add(UsageEvent(item_id=items_a[i].id, operator_id=op.id,
                             event_date=TODAY, outcome=Outcome.LOST,
                             loss_reason_id=lr.id))
        s.add(UsageEvent(item_id=items_a[5].id, operator_id=op.id,
                         event_date=TODAY, outcome=Outcome.SUCCESS,
                         aborted=True, abort_reason="ew_jam"))
        # Type B: 1 success — must NOT leak into type-A stats.
        s.add(UsageEvent(item_id=item_b.id, operator_id=op.id,
                         event_date=TODAY, outcome=Outcome.SUCCESS))
        # Old event outside 90-day window — must not be counted.
        s.add(UsageEvent(item_id=items_a[0].id, operator_id=op.id,
                         event_date=TODAY - timedelta(days=200),
                         outcome=Outcome.LOST, loss_reason_id=lr.id))

        # Signals: one matching "сектор", one open unrelated, one dismissed.
        s.add_all([
            PreTaskSignal(kind=SignalKind.WARNING,
                          title="РЕБ у секторі Б",
                          description="нова частота глушіння",
                          status=SignalStatus.NEW),
            PreTaskSignal(kind=SignalKind.INFO, title="Погода",
                          status=SignalStatus.ACKNOWLEDGED),
            PreTaskSignal(kind=SignalKind.RISK, title="сектор Б старий ризик",
                          status=SignalStatus.DISMISSED),
        ])

        # Assets: validated matching, validated unrelated, draft matching (must hide).
        s.add_all([
            ContextAsset(type=ContextAssetType.FAILURE_PATTERN,
                         title="Втрати у секторі Б вночі",
                         description="патерн", source="t", source_agent="t",
                         status=AssetStatus.VALIDATED, reusable_for=[]),
            ContextAsset(type=ContextAssetType.FAILURE_PATTERN,
                         title="Інше", description="x", source="t",
                         source_agent="t", status=AssetStatus.VALIDATED,
                         reusable_for=[]),
            ContextAsset(type=ContextAssetType.FAILURE_PATTERN,
                         title="ЧЕРНЕТКА про сектор Б", description="draft",
                         source="t", source_agent="t",
                         status=AssetStatus.DRAFT, reusable_for=[]),
        ])

        # Case with a validated lesson about сектор + open recommendation.
        case = AARCase(title="Кейс сектор Б", trigger=TriggerType.MANUAL,
                       status=CaseStatus.VALIDATED,
                       lesson_identified="Ротація частот у секторі Б",
                       analysis="аналіз", opr="Оперативний відділ")
        s.add(case)
        await s.flush()
        s.add(Recommendation(case_id=case.id, text="Змінити частоти в секторі"))
        await s.commit()


async def test_brief_stats_filtered_by_item_type_and_window() -> None:
    await _seed_world()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/briefing/mission", params={"item_type_code": "A"})
        assert r.status_code == 200, r.text
        st = r.json()["stats"]
        assert st["launched"] == 5      # aborted не входить, тип B не входить
        assert st["success"] == 3
        assert st["lost"] == 2
        assert st["aborted"] == 1
        assert abs(st["msr"] - 0.6) < 1e-6
        assert st["top_loss_reasons"] == ["c (×2)"]


async def test_brief_query_ranks_and_filters_sections() -> None:
    await _seed_world()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/briefing/mission", params={"q": "сектор Б"})
        body = r.json()

        # Signals: only OPEN ones that match; dismissed never appears.
        titles = [s["title"] for s in body["signals"]]
        assert "РЕБ у секторі Б" in titles
        assert "Погода" not in titles          # не матчить запит
        assert all("старий ризик" not in t for t in titles)  # dismissed

        # Validated-only lessons (draft must be hidden even if it matches).
        lesson_titles = [a["title"] for a in body["validated_lessons"]]
        assert "Втрати у секторі Б вночі" in lesson_titles
        assert all("ЧЕРНЕТКА" not in t for t in lesson_titles)

        # Case lesson + open recommendation surfaced.
        assert any("Ротація частот" in c["title"] for c in body["case_lessons"])
        assert any("Змінити частоти" in x["title"]
                   for x in body["open_recommendations"])


async def test_brief_without_query_returns_latest_open_items() -> None:
    await _seed_world()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/briefing/mission")
        body = r.json()
        # Без запиту — всі відкриті сигнали (2 з 3; dismissed схований).
        assert len(body["signals"]) == 2
        assert len(body["validated_lessons"]) == 2  # обидва validated, draft — ні


async def test_aborted_loss_surfaces_in_loss_reasons() -> None:
    """A loss during an aborted sortie (ADR-012 allows aborted+lost) must still
    appear in top_loss_reasons and lost_during_abort — otherwise an EW-heavy
    profile briefs as lost=0, hiding the exact risk the brief exists to show."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="A")
        op = Operator(code="E-01", name_uk="01")
        lr = LossReason(code="c", name_uk="c", zone=Zone.OPERATOR)
        s.add_all([a, op, lr])
        await s.flush()
        items = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(4)]
        s.add_all(items)
        await s.flush()
        s.add_all([
            # 1 clean launch+success, 1 non-aborted loss(c), 2 aborted losses(c).
            UsageEvent(item_id=items[0].id, operator_id=op.id,
                       event_date=TODAY, outcome=Outcome.SUCCESS),
            UsageEvent(item_id=items[1].id, operator_id=op.id,
                       event_date=TODAY, outcome=Outcome.LOST, loss_reason_id=lr.id),
            UsageEvent(item_id=items[2].id, operator_id=op.id,
                       event_date=TODAY, outcome=Outcome.LOST,
                       loss_reason_id=lr.id, aborted=True, abort_reason="ew_jam"),
            UsageEvent(item_id=items[3].id, operator_id=op.id,
                       event_date=TODAY, outcome=Outcome.LOST,
                       loss_reason_id=lr.id, aborted=True, abort_reason="ew_jam"),
        ])
        await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        st = (await client.get("/briefing/mission")).json()["stats"]
        assert st["launched"] == 2          # 1 success + 1 non-aborted loss
        assert st["lost"] == 1              # non-aborted losses only
        assert st["aborted"] == 2
        assert st["lost_during_abort"] == 2
        # top_loss_reasons must reflect ALL 3 losses, not just the 1 launched loss.
        assert st["top_loss_reasons"] == ["c (×3)"]


async def test_synthesis_returns_503_when_llm_disabled() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/briefing/mission/synthesis", params={"q": "сектор Б"})
        assert r.status_code == 503
        assert "LLM disabled" in r.json()["detail"]


async def test_synthesis_with_mocked_llm() -> None:
    await _seed_world()
    fake = llm_service.LLMResult(
        task_output=llm_service.MissionSynthesis(
            headline="Профіль підвищеного ризику РЕБ у секторі Б.",
            key_risks=[
                llm_service.SynthRisk(
                    risk="Втрати від РЕБ",
                    evidence="сигнал про нову частоту + урок про нічні втрати",
                    mitigation="ротація частот, нічна підготовка",
                )
            ],
            precautions=["Перевірити робочу частоту", "Підтвердити нічний навик обслуги"],
            confidence_note="Мало даних по типу B за профілем.",
        ),
        context_assets=[],
    )
    with patch.object(llm_service, "synthesize_mission_brief", return_value=fake) as m:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(
                "/briefing/mission/synthesis", params={"q": "сектор Б"}
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["headline"].startswith("Профіль")
            assert len(body["key_risks"]) == 1
            assert body["key_risks"][0]["mitigation"]
            assert len(body["precautions"]) == 2
            # The service was fed a compact payload built from the computed brief.
            payload = m.call_args.kwargs["brief_payload"]
            assert "stats" in payload and "active_signals" in payload
            assert payload["profile"]["query"] == "сектор Б"
