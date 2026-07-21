"""Wave 6 — pre-task proactive signals (docs/concept/positioning.md)."""
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase
from aar_api.models.audit import AuditAction, AuditLog


async def test_create_and_list_signal() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/signals",
            json={
                "kind": "warning",
                "title": "РЕБ-активність у секторі Б",
                "description": "Перед завданням: у секторі Б фіксується нова частота глушіння.",
                "author": None,
                "task_context": "Виліт 20.07, сектор Б",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "new"
        assert body["author"] is None  # анонімний сигнал допускається

        listed = (await client.get("/signals", params={"kind": "warning"})).json()
        assert any(s["id"] == body["id"] for s in listed)
        # Filter by status works too.
        none_left = (await client.get("/signals", params={"status": "accepted"})).json()
        assert all(s["status"] == "accepted" for s in none_left)


async def test_review_lifecycle_and_terminal_guard() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = (
            await client.post(
                "/signals", json={"kind": "proposal", "title": "Змінити частоти"}
            )
        ).json()["id"]

        # NEW → ACKNOWLEDGED → ACCEPTED
        r = await client.post(
            f"/signals/{sid}/review", json={"status": "acknowledged"}
        )
        assert r.status_code == 200
        r = await client.post(
            f"/signals/{sid}/review",
            json={"status": "accepted", "review_note": "внесено у план підготовки"},
        )
        assert r.status_code == 200
        assert r.json()["review_note"] == "внесено у план підготовки"
        assert r.json()["reviewed_at"] is not None

        # Terminal → further review is rejected.
        r = await client.post(f"/signals/{sid}/review", json={"status": "dismissed"})
        assert r.status_code == 409

        # Review cannot set NEW or CONVERTED directly.
        sid2 = (
            await client.post("/signals", json={"kind": "info", "title": "x"})
        ).json()["id"]
        r = await client.post(f"/signals/{sid2}/review", json={"status": "converted"})
        assert r.status_code == 422


async def test_convert_creates_prefilled_case_and_links() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = (
            await client.post(
                "/signals",
                json={
                    "kind": "risk",
                    "title": "Партія B-2026-07 має відхилення",
                    "description": "Три вироби з партії показали дрейф гіроскопа на стенді.",
                },
            )
        ).json()["id"]

        r = await client.post(f"/signals/{sid}/convert")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "converted"
        assert body["case_id"] is not None

        # The case exists and carries the signal's observation.
        Session = async_sessionmaker(_engine, expire_on_commit=False)
        async with Session() as s:
            case = await s.get(AARCase, body["case_id"])
            assert case is not None
            assert "Сигнал:" in case.title
            assert "дрейф гіроскопа" in (case.what_happened or "")
            audit = list(
                await s.scalars(
                    select(AuditLog).where(
                        AuditLog.action == AuditAction.SIGNAL_CONVERTED
                    )
                )
            )
            assert len(audit) == 1

        # Converted is terminal — cannot convert twice.
        r = await client.post(f"/signals/{sid}/convert")
        assert r.status_code == 409
