"""Audit-chain coverage for writes that were silently unrecorded.

`AuditAction.SUBSCRIPTION_CREATED` / `SUBSCRIPTION_DELETED` existed in the enum
but were never written by any code path — dead members are strong evidence the
audit was intended and forgotten. Manual context-asset creation was likewise
unrecorded while the LLM path (`persist_drafts`) did record it, so the chain's
coverage of asset provenance depended on which path produced the row.
"""
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.audit import AuditAction, AuditLog

_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def _actions() -> list[AuditAction]:
    async with _Session() as s:
        rows = list(await s.scalars(select(AuditLog).order_by(AuditLog.id)))
    return [r.action for r in rows]


async def _payload_for(action: AuditAction) -> dict:
    async with _Session() as s:
        rows = list(
            await s.scalars(select(AuditLog).where(AuditLog.action == action))
        )
    assert rows, f"no audit entry for {action}"
    return dict(rows[-1].payload)


async def test_subscription_create_and_delete_reach_the_chain() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/integrations/subscriptions",
            json={
                "name": "delta-test",
                "kind": "delta",
                "target_url": "https://delta.example/hook",
                "secret": "s3cret-value",
                "events": ["usage_event.created"],
                "active": True,
            },
        )
        assert created.status_code in (200, 201), created.text
        sub_id = created.json()["id"]

        payload = await _payload_for(AuditAction.SUBSCRIPTION_CREATED)
        assert payload["name"] == "delta-test"
        assert payload["target_url"] == "https://delta.example/hook"
        # The shared secret must never be copied into the chain: audit rows are
        # readable by analysts, and the chain is append-only, so a leaked
        # secret there could not be redacted afterwards.
        assert "secret" not in payload
        assert "s3cret-value" not in str(payload)

        deleted = await client.delete(f"/integrations/subscriptions/{sub_id}")
        assert deleted.status_code in (200, 204), deleted.text

    actions = await _actions()
    assert AuditAction.SUBSCRIPTION_CREATED in actions
    assert AuditAction.SUBSCRIPTION_DELETED in actions


async def test_manual_context_asset_creation_is_audited() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/context/assets",
            json={
                "type": "failure_pattern",
                "title": "Втрата зв'язку над лісом",
                "description": "Повторюваний патерн на трьох вильотах.",
                "source": "manual",
            },
        )
        assert r.status_code in (200, 201), r.text

    payload = await _payload_for(AuditAction.CONTEXT_ASSET_CREATED)
    assert payload["type"] == "failure_pattern"
    assert payload["title"] == "Втрата зв'язку над лісом"


async def test_audit_chain_stays_verifiable_after_the_new_entries() -> None:
    """New appends must not break the hash chain they extend."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sub = await client.post(
            "/integrations/subscriptions",
            json={
                "name": "chain-check",
                "kind": "generic",
                "target_url": "https://example.test/hook",
                "events": ["usage_event.created"],
                "active": True,
            },
        )
        assert sub.status_code in (200, 201), sub.text
        # `description` is required (min_length=1) — asserting the status here
        # is what caught this test silently writing only one chain entry.
        asset = await client.post(
            "/context/assets",
            json={
                "type": "edge_case",
                "title": "Межовий випадок",
                "description": "Опис межового випадку.",
                "source": "manual",
            },
        )
        assert asset.status_code in (200, 201), asset.text
        verified = await client.get("/audit/verify")
        assert verified.status_code == 200, verified.text
        body = verified.json()
        assert body["ok"] is True, body
        assert body["checked"] >= 2
