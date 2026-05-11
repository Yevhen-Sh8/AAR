from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason, Zone


async def _seed_minimal() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(
            [
                ItemType(code="A", name_uk="Виріб А"),
                Operator(code="E-01", name_uk="Експлуатант 01"),
                LossReason(code="a", name_uk="Причина a", zone=Zone.EXTERNAL),
                RepairReason(code="a", name_uk="Причина a", zone=Zone.OPERATOR),
            ]
        )
        await s.commit()


async def test_create_and_list_event() -> None:
    await _seed_minimal()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/events",
            json={
                "item_serial_no": "A-00001",
                "item_type_code": "A",
                "operator_code": "E-01",
                "event_date": str(date(2025, 11, 5)),
                "outcome": "success",
            },
        )
        assert r.status_code == 201, r.text
        r = await client.get("/events")
        assert r.status_code == 200
        assert len(r.json()) == 1


async def test_event_validation_requires_reason() -> None:
    await _seed_minimal()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/events",
            json={
                "item_serial_no": "A-00002",
                "item_type_code": "A",
                "operator_code": "E-01",
                "event_date": str(date(2025, 11, 5)),
                "outcome": "lost",
            },
        )
        assert r.status_code == 422


