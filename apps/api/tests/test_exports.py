from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason, Zone
from aar_api.models.event import Item, Outcome, UsageEvent


async def _seed() -> dict[str, int]:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="Виріб типу А")
        op = Operator(code="E-01", name_uk="Експлуатант 01")
        lr = LossReason(code="a", name_uk="Помилка обслуги", zone=Zone.OPERATOR)
        rr = RepairReason(code="b", name_uk="Відмова блоку живлення", zone=Zone.MANUFACTURER)
        s.add_all([a, op, lr, rr])
        await s.flush()
        items = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(5)]
        s.add_all(items)
        await s.flush()
        success_ev = UsageEvent(
            item_id=items[0].id, operator_id=op.id,
            event_date=date(2025, 11, 10), outcome=Outcome.SUCCESS,
        )
        loss_ev = UsageEvent(
            item_id=items[1].id, operator_id=op.id,
            event_date=date(2025, 11, 12),
            outcome=Outcome.LOST, loss_reason_id=lr.id,
        )
        repair_ev = UsageEvent(
            item_id=items[2].id, operator_id=op.id,
            event_date=date(2025, 11, 15),
            outcome=Outcome.REPAIR, repair_reason_id=rr.id,
        )
        s.add_all([success_ev, loss_ev, repair_ev])
        await s.commit()
        return {
            "success": success_ev.id,
            "loss": loss_ev.id,
            "repair": repair_ev.id,
        }


async def test_inventory_xlsx() -> None:
    await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/exports/mod440/inventory.xlsx",
            params={"unit_name": "А1234", "as_of": "2025-12-01"},
        )
        assert r.status_code == 200, r.text
        assert r.content[:2] == b"PK"
        assert "inventory-2025-12-01.xlsx" in r.headers["content-disposition"]


async def test_movement_xlsx_includes_events_in_range() -> None:
    await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/exports/mod440/movement.xlsx",
            params={
                "date_from": "2025-11-01",
                "date_to": "2025-11-30",
                "unit_name": "А1234",
            },
        )
        assert r.status_code == 200, r.text
        assert r.content[:2] == b"PK"


async def test_loss_act_docx() -> None:
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/exports/mod440/loss-act/{ids['loss']}.docx",
            params={
                "unit_name": "А1234",
                "responsible_person": "Іванов І.І.",
                "circumstances": "Враження засобами РЕБ під час виконання завдання",
            },
        )
        assert r.status_code == 200, r.text
        assert r.content[:2] == b"PK"  # docx is also a zip
        assert "loss-act" in r.headers["content-disposition"]


async def test_loss_act_rejects_success_event() -> None:
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/exports/mod440/loss-act/{ids['success']}.docx")
        assert r.status_code == 400
        assert "not a loss" in r.json()["detail"]


async def test_repair_act_docx() -> None:
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/exports/mod440/repair-act/{ids['repair']}.docx",
            params={
                "sender": "ст. сержант Петренко",
                "receiver": "майстер Сидоренко",
                "defect_description": "Не виходить на робочий режим, КЗ у блоці живлення",
            },
        )
        assert r.status_code == 200, r.text
        assert r.content[:2] == b"PK"
