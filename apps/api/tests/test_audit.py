from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.audit import AuditAction, AuditLog
from aar_api.models.dictionaries import ItemType, LossReason, Operator, Zone
from aar_api.services.audit import GENESIS, append, verify_chain


async def _seed_dicts() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(
            [
                ItemType(code="A", name_uk="A"),
                Operator(code="E-01", name_uk="01"),
                LossReason(code="a", name_uk="a", zone=Zone.OPERATOR),
            ]
        )
        await s.commit()


async def test_chain_extends_and_verifies() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        e1 = await append(
            s, action=AuditAction.EVENT_CREATED,
            entity_type="usage_event", entity_id=1,
            payload={"outcome": "success"},
        )
        e2 = await append(
            s, action=AuditAction.CASE_CREATED,
            entity_type="aar_case", entity_id=42,
            payload={"title": "test"},
        )
        await s.commit()
        assert e1.prev_hash == GENESIS
        assert e2.prev_hash == e1.entry_hash
        status = await verify_chain(s)
        assert status.ok, status.message
        assert status.checked == 2


async def test_tampering_breaks_chain() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        await append(
            s, action=AuditAction.EVENT_CREATED,
            entity_type="usage_event", entity_id=1, payload={},
        )
        await append(
            s, action=AuditAction.CASE_CREATED,
            entity_type="aar_case", entity_id=42, payload={"title": "ok"},
        )
        await s.commit()

    async with Session() as s:
        # Tamper: change payload of the first row without recomputing entry_hash
        row = await s.scalar(select(AuditLog).order_by(AuditLog.id).limit(1))
        assert row is not None
        row.payload = {"outcome": "TAMPERED"}
        await s.commit()

    async with Session() as s:
        status = await verify_chain(s)
        assert not status.ok
        assert status.broken_at_id == 1
        assert "entry_hash mismatch" in status.message


async def test_event_creation_writes_audit_entry() -> None:
    await _seed_dicts()
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

        r2 = await client.get("/audit/log")
        assert r2.status_code == 200, r2.text
        entries = r2.json()
        assert any(e["action"] == "event.created" for e in entries)

        r3 = await client.get("/audit/verify")
        assert r3.status_code == 200
        body = r3.json()
        assert body["ok"] is True, body
        assert body["checked"] >= 1


async def test_rbac_blocks_unauthenticated_in_prod(monkeypatch) -> None:
    from aar_api.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("AAR_ENVIRONMENT", "production")
    monkeypatch.setenv("AAR_JWT_SECRET", "real-secret")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/audit/log")
            assert r.status_code == 401, r.text
    finally:
        config.get_settings.cache_clear()
