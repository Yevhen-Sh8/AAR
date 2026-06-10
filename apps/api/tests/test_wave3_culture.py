"""Tests for Wave 3 — culture and dissemination."""
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase, TriggerType
from aar_api.models.dictionaries import Operator
from aar_api.models.integration import Subscription, WebhookEventKind
from aar_api.models.user import User


async def _make_case() -> int:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        c = AARCase(title="t", trigger=TriggerType.MANUAL)
        s.add(c)
        await s.commit()
        return c.id


async def test_request_reports_creates_pending_stubs() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            User(email=f"u{i}@example.com", full_name=f"u{i}",
                 hashed_password="x", role="analyst")
            for i in range(3)
        ])
        await s.commit()
    case_id = await _make_case()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/aar/cases/{case_id}/request-reports",
            json={"user_ids": [1, 2, 3]},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["requested_count"] == 3
        assert body["skipped_existing"] == 0
        assert len(body["pending_report_ids"]) == 3

        # Idempotency: a second call with the same users skips them.
        r2 = await client.post(
            f"/aar/cases/{case_id}/request-reports",
            json={"user_ids": [1, 2]},
        )
        assert r2.status_code == 201
        assert r2.json()["requested_count"] == 0
        assert r2.json()["skipped_existing"] == 2


async def test_submit_report_fills_pending_stub() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(User(email="u1@example.com", full_name="u1",
                   hashed_password="x", role="analyst"))
        await s.commit()
    case_id = await _make_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/aar/cases/{case_id}/request-reports", json={"user_ids": [1]}
        )
        stub_id = r.json()["pending_report_ids"][0]

        r = await client.post(
            f"/aar/cases/{case_id}/reports",
            json={
                "user_id": 1,
                "anonymous": False,
                "what_happened": "ось так",
                "why": "тому що",
                "request_id": stub_id,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["id"] == stub_id
        assert body["submitted_at"] is not None
        assert body["requested_at"] is not None
        assert body["what_happened"] == "ось так"

        # Second submit for the same stub is rejected (already submitted).
        r2 = await client.post(
            f"/aar/cases/{case_id}/reports",
            json={"user_id": 1, "request_id": stub_id, "what_happened": "ще раз"},
        )
        assert r2.status_code == 409


async def test_anonymous_report_redacts_user_id() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(User(email="u@example.com", full_name="u",
                   hashed_password="x", role="analyst"))
        await s.commit()
    case_id = await _make_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/aar/cases/{case_id}/reports",
            json={
                "user_id": 1,
                "anonymous": True,
                "what_happened": "ось так",
                "why": "не важливо хто це сказав",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["anonymous"] is True
        assert body["user_id"] is None  # redacted on creation


async def test_notification_subscription_receives_case_created_event() -> None:
    """When a webhook subscription is active for aar_case.created and a case
    is created, a Delivery row is persisted (status FAILED since no real
    server, but the dispatch attempt was made and recorded)."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(Operator(code="E-01", name_uk="01"))
        s.add(
            Subscription(
                name="test-sub",
                kind="generic",
                target_url="http://127.0.0.1:9/never",
                events=[WebhookEventKind.AAR_CASE_CREATED.value],
                active=True,
            )
        )
        await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/aar/cases",
            json={"title": "Ручний кейс", "operator_code": "E-01"},
        )
        assert r.status_code == 201, r.text
        # Verify a Delivery was attempted.
        deliveries = (
            await client.get("/integrations/deliveries", params={"limit": 5})
        ).json()
        assert any(
            d["event_kind"] == WebhookEventKind.AAR_CASE_CREATED.value
            for d in deliveries
        )


async def test_notification_fires_on_case_transition() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(
            Subscription(
                name="trans-sub",
                kind="generic",
                target_url="http://127.0.0.1:9/never",
                events=[WebhookEventKind.AAR_CASE_TRANSITIONED.value],
                active=True,
            )
        )
        await s.commit()
    case_id = await _make_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/aar/cases/{case_id}/transition", json={"to": "analysed"}
        )
        assert r.status_code == 200
        deliveries = (
            await client.get("/integrations/deliveries", params={"limit": 5})
        ).json()
        assert any(
            d["event_kind"] == WebhookEventKind.AAR_CASE_TRANSITIONED.value
            for d in deliveries
        )


async def test_pending_reports_listed_for_case() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            User(email=f"u{i}@example.com", full_name=f"u{i}",
                 hashed_password="x", role="analyst")
            for i in range(2)
        ])
        await s.commit()
    case_id = await _make_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/aar/cases/{case_id}/request-reports", json={"user_ids": [1, 2]}
        )
        reports = (await client.get(f"/aar/cases/{case_id}/reports")).json()
        assert len(reports) == 2
        assert all(r["submitted_at"] is None for r in reports)
        assert all(r["requested_at"] is not None for r in reports)
