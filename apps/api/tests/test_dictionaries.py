"""Dictionary CRUD: create/update/delete, uniqueness, in-use guard, audit."""
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.audit import AuditAction, AuditLog
from aar_api.models.event import Item


async def test_item_type_create_update_delete_roundtrip() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # create
        r = await client.post(
            "/dictionaries/item-types",
            json={"code": "FPV", "name_uk": "FPV-дрон", "unit_cost_usd": "450.00"},
        )
        assert r.status_code == 201, r.text
        obj = r.json()
        assert obj["code"] == "FPV"
        assert obj["unit_cost_usd"] == "450.00"

        # duplicate code -> 409
        dup = await client.post(
            "/dictionaries/item-types", json={"code": "FPV", "name_uk": "інший"}
        )
        assert dup.status_code == 409

        # partial update: name + cost; code stays
        upd = await client.patch(
            f"/dictionaries/item-types/{obj['id']}",
            json={"name_uk": "FPV-дрон (7\")", "unit_cost_usd": "500.00"},
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["name_uk"] == 'FPV-дрон (7")'
        assert upd.json()["unit_cost_usd"] == "500.00"
        assert upd.json()["code"] == "FPV"  # immutable

        # delete (unreferenced) -> 200 {"deleted": id}
        d = await client.delete(f"/dictionaries/item-types/{obj['id']}")
        assert d.status_code == 200
        assert d.json()["deleted"] == obj["id"]

        listed = (await client.get("/dictionaries/item-types")).json()
        assert all(x["code"] != "FPV" for x in listed)


async def test_delete_refused_when_referenced() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = (
            await client.post(
                "/dictionaries/item-types",
                json={"code": "MZR", "name_uk": "Тип у вжитку"},
            )
        ).json()

        # reference it from an items row directly
        maker = async_sessionmaker(_engine, expire_on_commit=False)
        async with maker() as session:
            session.add(Item(serial_no="SN-REF-1", item_type_id=created["id"]))
            await session.commit()

        # delete now refused with 409
        d = await client.delete(f"/dictionaries/item-types/{created['id']}")
        assert d.status_code == 409
        assert "видалення заборонено" in d.json()["detail"]

        # still listed
        listed = (await client.get("/dictionaries/item-types")).json()
        assert any(x["code"] == "MZR" for x in listed)


async def test_reason_zone_and_audit_chain() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/dictionaries/loss-reasons",
            json={"code": "z9", "name_uk": "Збиття ППО", "zone": "external"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["zone"] == "external"

        # update the zone
        upd = await client.patch(
            f"/dictionaries/loss-reasons/{r.json()['id']}", json={"zone": "unknown"}
        )
        assert upd.status_code == 200
        assert upd.json()["zone"] == "unknown"

    # audit entries were written for create + update
    maker = async_sessionmaker(_engine, expire_on_commit=False)
    async with maker() as session:
        rows = list(await session.scalars(select(AuditLog)))
    actions = {row.action for row in rows}
    assert AuditAction.DICTIONARY_CREATED in actions
    assert AuditAction.DICTIONARY_UPDATED in actions


