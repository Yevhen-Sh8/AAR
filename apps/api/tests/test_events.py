from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason, Zone
from aar_api.models.event import UsageEvent


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




async def test_event_idempotent_via_client_event_id() -> None:
    await _seed_minimal()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = {
            "item_serial_no": "A-00099",
            "item_type_code": "A",
            "operator_code": "E-01",
            "event_date": str(date(2025, 11, 5)),
            "outcome": "success",
            "client_event_id": "uuid-fixed-1",
        }
        r1 = await client.post("/events", json=body)
        assert r1.status_code == 201, r1.text
        first_id = r1.json()["id"]
        r2 = await client.post("/events", json=body)
        assert r2.status_code in (200, 201)
        assert r2.json()["id"] == first_id
        listing = (await client.get("/events")).json()
        assert sum(1 for e in listing if e["client_event_id"] == "uuid-fixed-1") == 1


async def test_aborted_flag_is_persisted() -> None:
    """`aborted` was accepted by the schema and dropped by the handler.

    Every event was therefore stored with aborted=False, which silently
    collapsed MSR-full onto MSR-narrow and zeroed every abort counter — the
    Wave 2 distinction existed only in the metric code, never in the data.
    """
    await _seed_minimal()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/events",
            json={
                "item_serial_no": "A-ABORT-1",
                "item_type_code": "A",
                "operator_code": "E-01",
                "event_date": "2026-06-01",
                "outcome": "lost",
                "loss_reason_code": "a",
                "aborted": True,
                "abort_reason": "РЕБ на маршруті",
            },
        )
        assert r.status_code == 201, r.text

    async with async_sessionmaker(_engine, expire_on_commit=False)() as s:
        ev = await s.scalar(
            select(UsageEvent).where(UsageEvent.client_event_id.is_(None))
        )
        assert ev is not None
        assert ev.aborted is True, "aborted must survive the round-trip"
        assert ev.abort_reason == "РЕБ на маршруті"
