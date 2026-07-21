"""Geo map data source — GET /events/geojson."""
from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.dictionaries import ItemType, LossReason, Operator, Zone
from aar_api.models.event import Item, Outcome, UsageEvent


async def _seed() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        a = ItemType(code="A", name_uk="A")
        op = Operator(code="E-01", name_uk="01")
        lr = LossReason(code="c", name_uk="c", zone=Zone.OPERATOR)
        s.add_all([a, op, lr])
        await s.flush()
        items = [Item(serial_no=f"A-{i:05d}", item_type_id=a.id) for i in range(3)]
        s.add_all(items)
        await s.flush()
        s.add_all([
            UsageEvent(item_id=items[0].id, operator_id=op.id, event_date=date(2026, 1, 5),
                       outcome=Outcome.SUCCESS,
                       location={"type": "Point", "coordinates": [30.52, 50.45]}),
            UsageEvent(item_id=items[1].id, operator_id=op.id, event_date=date(2026, 1, 6),
                       outcome=Outcome.LOST, loss_reason_id=lr.id,
                       location={"type": "Point", "coordinates": [36.23, 49.99]}),
            # No location — must be excluded from the map.
            UsageEvent(item_id=items[2].id, operator_id=op.id, event_date=date(2026, 1, 7),
                       outcome=Outcome.SUCCESS),
        ])
        await s.commit()


async def test_geojson_returns_only_located_events_with_codes() -> None:
    await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/events/geojson")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["type"] == "FeatureCollection"
        assert body["count"] == 2  # the location-less event is excluded
        f = body["features"][0]
        assert f["geometry"]["type"] == "Point"
        props = f["properties"]
        assert props["operator_code"] == "E-01"
        assert props["item_type_code"] == "A"
        assert props["serial_no"].startswith("A-")
        assert props["outcome"] in ("success", "lost")


async def test_geojson_filters_by_outcome() -> None:
    await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/events/geojson", params={"outcome": "lost"})
        body = r.json()
        assert body["count"] == 1
        assert body["features"][0]["properties"]["outcome"] == "lost"
