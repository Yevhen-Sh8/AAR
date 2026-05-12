from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.dictionaries import ItemType, LossReason, Operator, Zone
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.services import integrations as integ_svc


async def _seed() -> dict[str, int]:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            ItemType(code="A", name_uk="A"),
            Operator(code="E-01", name_uk="01"),
            LossReason(code="a", name_uk="РЕБ", zone=Zone.EXTERNAL),
        ])
        await s.flush()
        a = await s.scalar(select(ItemType).where(ItemType.code == "A"))
        op = await s.scalar(select(Operator).where(Operator.code == "E-01"))
        assert a and op
        item = Item(serial_no="A-00001", item_type_id=a.id)
        s.add(item)
        await s.flush()
        ev = UsageEvent(
            item_id=item.id,
            operator_id=op.id,
            event_date=date(2025, 12, 15),
            outcome=Outcome.SUCCESS,
            location={"type": "Point", "coordinates": [30.5234, 50.4501]},
        )
        s.add(ev)
        await s.commit()
        return {"event_id": ev.id}


async def test_subscription_crud() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/integrations/subscriptions",
            json={
                "name": "delta-pilot",
                "kind": "delta",
                "target_url": "https://delta.example.com/hook",
                "events": ["usage_event.created"],
                "secret": "s3cret",
            },
        )
        assert r.status_code == 201, r.text
        sub_id = r.json()["id"]

        listing = (await client.get("/integrations/subscriptions")).json()
        assert any(s["id"] == sub_id for s in listing)

        d = await client.delete(f"/integrations/subscriptions/{sub_id}")
        assert d.status_code == 204


async def test_preview_delta_wraps_geojson() -> None:
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/integrations/preview",
            params={"kind": "delta", "event_id": ids["event_id"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["geojson"]["type"] == "FeatureCollection"
        feature = body["geojson"]["features"][0]
        assert feature["geometry"]["type"] == "Point"
        assert feature["geometry"]["coordinates"] == [30.5234, 50.4501]


async def test_preview_sap_is_flat() -> None:
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/integrations/preview",
            params={"kind": "sap", "event_id": ids["event_id"]},
        )
        body = r.json()
        assert body["EventType"] == "usage_event.created"
        assert body["Outcome"] == "success"
        assert "ItemID" in body


async def test_dispatch_records_delivery_and_signs(monkeypatch) -> None:
    ids = await _seed()
    transport = ASGITransport(app=app)
    captured: dict[str, object] = {}

    async def fake_post(
        sub, body, *, client
    ) -> tuple[int | None, str | None]:
        captured["url"] = sub.target_url
        captured["body"] = body
        captured["sig"] = integ_svc.sign(sub.secret, body) if sub.secret else None
        return 202, None

    monkeypatch.setattr(integ_svc, "_post", fake_post)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sub = await client.post(
            "/integrations/subscriptions",
            json={
                "name": "delta-pilot",
                "kind": "delta",
                "target_url": "https://delta.example.com/hook",
                "events": ["usage_event.created"],
                "secret": "shh",
            },
        )
        assert sub.status_code == 201

        d = await client.post(f"/integrations/dispatch/{ids['event_id']}")
        assert d.status_code == 200, d.text
        deliveries = d.json()
        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "delivered"
        assert deliveries[0]["response_code"] == 202

    expected_sig = integ_svc.sign("shh", captured["body"])
    assert captured["sig"] == expected_sig
    assert "delta.example.com" in captured["url"]


async def test_inbound_event_creates_usage_event() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            ItemType(code="A", name_uk="A"),
            Operator(code="E-09", name_uk="09"),
        ])
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/integrations/inbound/events",
            json={
                "source": "odin",
                "external_id": "odin-12345",
                "item_serial_no": "A-99999",
                "item_type_code": "A",
                "operator_code": "E-09",
                "event_date": "2025-12-16",
                "outcome": "success",
                "location": {"type": "Point", "coordinates": [35.0, 49.5]},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"] == "odin"

        # Idempotent: same (source, external_id) returns the same row
        r2 = await client.post(
            "/integrations/inbound/events",
            json={
                "source": "odin",
                "external_id": "odin-12345",
                "item_serial_no": "A-99999",
                "item_type_code": "A",
                "operator_code": "E-09",
                "event_date": "2025-12-16",
                "outcome": "success",
            },
        )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("duplicate") is True
        assert r2.json()["id"] == body["id"]


async def test_geojson_export_filters_events_with_location() -> None:
    await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/integrations/events.geojson",
            params={"date_from": "2025-12-01", "date_to": "2025-12-31"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "FeatureCollection"
        assert len(body["features"]) >= 1
        f = body["features"][0]
        assert f["type"] == "Feature"
        assert f["geometry"]["type"] == "Point"


async def test_connectors_endpoint_excludes_oberig() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/integrations/connectors")
        body = r.json()
        assert "oberig" in body["excluded"]
        assert "oberig" not in body["kinds"]
        assert "delta" in body["kinds"]
        assert "kropyva" in body["kinds"]
        assert "odin" in body["kinds"]
        assert "sap" in body["kinds"]
