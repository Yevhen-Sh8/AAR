from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason, Zone
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.models.user import User

TODAY = date(2025, 12, 15)


async def _seed_t1() -> None:
    """E-01: 3 consecutive days with Кеф_обсл below 0.70 (operator-zone losses)."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="A")
        e1 = Operator(code="E-01", name_uk="01")
        lr_op = LossReason(code="op", name_uk="op", zone=Zone.OPERATOR)
        s.add_all([a, e1, lr_op])
        await s.flush()
        items = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(30)]
        s.add_all(items)
        await s.flush()
        idx = 0
        for offset in (2, 1, 0):
            d = TODAY - timedelta(days=offset)
            # 5 launches, 2 success, 3 operator-zone losses → Кеф_обсл = 2/5 = 0.4
            for _ in range(2):
                s.add(UsageEvent(item_id=items[idx].id, operator_id=e1.id,
                                 event_date=d, outcome=Outcome.SUCCESS))
                idx += 1
            for _ in range(3):
                s.add(UsageEvent(item_id=items[idx].id, operator_id=e1.id,
                                 event_date=d, outcome=Outcome.LOST,
                                 loss_reason_id=lr_op.id))
                idx += 1
        await s.commit()


async def _seed_t3() -> None:
    """Serial A-00001 has 2 repair returns in the window."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="A")
        e1 = Operator(code="E-01", name_uk="01")
        rr = RepairReason(code="x", name_uk="x", zone=Zone.OPERATOR)
        s.add_all([a, e1, rr])
        await s.flush()
        bad = Item(serial_no="A-00001", item_type_id=a.id)
        s.add(bad)
        await s.flush()
        s.add_all([
            UsageEvent(item_id=bad.id, operator_id=e1.id,
                       event_date=TODAY - timedelta(days=5),
                       outcome=Outcome.REPAIR, repair_reason_id=rr.id),
            UsageEvent(item_id=bad.id, operator_id=e1.id,
                       event_date=TODAY - timedelta(days=1),
                       outcome=Outcome.REPAIR, repair_reason_id=rr.id),
        ])
        await s.commit()


async def test_trigger_t1_creates_keff_drop_case() -> None:
    await _seed_t1()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/aar/run-triggers", params={"today": TODAY.isoformat()})
        assert r.status_code == 200, r.text
        assert len(r.json()["created_case_ids"]) >= 1
        cases = (await client.get("/aar/cases")).json()
        assert any("E-01" in c["title"] and c["trigger"] == "keff_drop" for c in cases)

        # Idempotent: second run skips
        r2 = await client.post("/aar/run-triggers", params={"today": TODAY.isoformat()})
        assert r2.json()["skipped_existing"] >= 1


async def test_trigger_t3_item_anomaly() -> None:
    await _seed_t3()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/aar/run-triggers", params={"today": TODAY.isoformat()})
        cases = (await client.get("/aar/cases")).json()
        assert any(c["trigger"] == "item_anomaly" and "A-00001" in c["title"] for c in cases)
        assert r.status_code == 200


async def test_manual_case_with_report_and_recommendation() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            Operator(code="E-01", name_uk="01"),
            User(email="m@example.com", full_name="Manager",
                 hashed_password="x", role="manager"),
        ])
        await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/aar/cases",
            json={"title": "Ручний кейс", "operator_code": "E-01", "summary": "тест"},
        )
        assert r.status_code == 201, r.text
        case_id = r.json()["id"]
        assert r.json()["trigger"] == "manual"

        r = await client.post(
            f"/aar/cases/{case_id}/reports",
            json={"user_id": 1, "what_happened": "ось так", "why": "тому що"},
        )
        assert r.status_code == 201

        r = await client.post(
            f"/aar/cases/{case_id}/recommendations",
            json={"text": "Провести довчання обслуги"},
        )
        assert r.status_code == 201
        rec_id = r.json()["id"]

        r = await client.patch(
            f"/aar/recommendations/{rec_id}", json={"status": "validated"}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "validated"
        assert r.json()["validated_at"] is not None

        r = await client.post(f"/aar/cases/{case_id}/close")
        assert r.status_code == 200
        assert r.json()["status"] == "closed"
