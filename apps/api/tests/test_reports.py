from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason, Zone
from aar_api.models.event import Item, Outcome, UsageEvent


async def _seed_day() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="A")
        e1 = Operator(code="E-01", name_uk="01")
        e2 = Operator(code="E-02", name_uk="02")
        lr = LossReason(code="a", name_uk="a", zone=Zone.OPERATOR)
        rr = RepairReason(code="a", name_uk="a", zone=Zone.OPERATOR)
        s.add_all([a, e1, e2, lr, rr])
        await s.flush()
        items = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(1, 11)]
        s.add_all(items)
        await s.flush()
        d = date(2025, 11, 15)
        # E-01: 5 launches: 3 success, 1 lost, 1 repair
        def ev(i: int, op_id: int, **kw: object) -> UsageEvent:
            return UsageEvent(item_id=items[i].id, operator_id=op_id, event_date=d, **kw)  # type: ignore[arg-type]

        s.add_all([
            ev(0, e1.id, outcome=Outcome.SUCCESS),
            ev(1, e1.id, outcome=Outcome.SUCCESS),
            ev(2, e1.id, outcome=Outcome.SUCCESS),
            ev(3, e1.id, outcome=Outcome.LOST, loss_reason_id=lr.id),
            ev(4, e1.id, outcome=Outcome.REPAIR, repair_reason_id=rr.id),
            ev(5, e2.id, outcome=Outcome.SUCCESS),
            ev(6, e2.id, outcome=Outcome.SUCCESS),
        ])
        await s.commit()


async def test_daily_report_aggregation() -> None:
    await _seed_day()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/reports/daily", params={"date": "2025-11-15"})
        assert r.status_code == 200, r.text
        body = r.json()
        rows = {row["operator_code"]: row for row in body["rows"]}
        assert rows["E-01"]["launched"] == 5
        assert rows["E-01"]["success"] == 3
        assert rows["E-01"]["lost"] == 1
        assert rows["E-01"]["repaired"] == 1
        assert abs(rows["E-01"]["keff"] - 0.6) < 1e-6
        assert rows["E-02"]["launched"] == 2
        assert body["totals"]["launched"] == 7
        assert body["totals"]["success"] == 5
        assert len(body["loss_details"]) == 1
        assert len(body["repair_breakdown"]) == 1


async def test_daily_xlsx_and_pdf() -> None:
    await _seed_day()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/reports/daily.xlsx", params={"date": "2025-11-15"})
        assert r.status_code == 200
        assert r.content[:2] == b"PK"  # xlsx is a zip
        r = await client.get("/reports/daily.pdf", params={"date": "2025-11-15"})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
