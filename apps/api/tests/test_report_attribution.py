"""Testimony must belong to the person who gave it.

`POST /aar/cases/{id}/reports` had an impersonation guard that only fired when
the caller volunteered a `user_id` — which the participant UI never sends. So
any logged-in participant could POST `{request_id: <colleague's stub>}` and the
append-only chain would record the COLLEAGUE as the author of words they never
said, and `/aar/my-observations` would later show that colleague «ось що вийшло
з вашого звіту».

Transcription on behalf of another stays allowed for ADMIN/MANAGER/ANALYST —
roster people deliberately have no account — but it is recorded as
`transcribed_by`, separate from `originator_user_id`.
"""
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.core.security import hash_password
from aar_api.main import app
from aar_api.models.aar import AARCase, IndividualReport, TriggerType
from aar_api.models.audit import AuditAction, AuditLog
from aar_api.models.user import Role, User

_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def _person(email: str, role: Role = Role.PARTICIPANT) -> int:
    async with _Session() as s:
        u = User(
            email=email,
            full_name=email.split("@")[0],
            role=role,
            hashed_password=hash_password("secret12"),
        )
        s.add(u)
        await s.flush()
        uid = u.id
        await s.commit()
    return uid


async def _stub_for(uid: int) -> tuple[int, int]:
    """A case with one pending report request addressed to `uid`."""
    async with _Session() as s:
        case = AARCase(title="Втрата над ціллю", trigger=TriggerType.MANUAL)
        s.add(case)
        await s.flush()
        stub = IndividualReport(
            case_id=case.id,
            requested_for_user_id=uid,
            requested_at=datetime.now(UTC),
        )
        s.add(stub)
        await s.flush()
        ids = (case.id, stub.id)
        await s.commit()
    return ids


async def _token(client: AsyncClient, email: str) -> str:
    r = await client.post("/auth/login", json={"email": email, "password": "secret12"})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


def _auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


async def test_participant_cannot_fill_a_colleagues_stub() -> None:
    victim = await _person("victim@aar.local")
    await _person("attacker@aar.local")
    case_id, stub_id = await _stub_for(victim)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        tok = await _token(c, "attacker@aar.local")
        r = await c.post(
            f"/aar/cases/{case_id}/reports",
            headers=_auth(tok),
            json={
                "request_id": stub_id,
                "what_happened": "Екіпаж усе зробив правильно, винен виріб.",
            },
        )
    assert r.status_code == 403, r.text
    assert "адресований іншій особі" in r.json()["detail"]

    # And nothing was written.
    async with _Session() as s:
        row = await s.get(IndividualReport, stub_id)
        assert row is not None
        assert row.submitted_at is None
        assert row.what_happened is None


async def test_the_addressee_fills_their_own_stub_and_is_recorded_as_author() -> None:
    uid = await _person("crew@aar.local")
    case_id, stub_id = await _stub_for(uid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        tok = await _token(c, "crew@aar.local")
        r = await c.post(
            f"/aar/cases/{case_id}/reports",
            headers=_auth(tok),
            json={"request_id": stub_id, "what_happened": "Зник звʼязок на підльоті"},
        )
    assert r.status_code == 201, r.text

    async with _Session() as s:
        row = await s.get(IndividualReport, stub_id)
        assert row is not None
        assert row.submitted_at is not None
        # A non-anonymous report has an author on the row, not just a stub target.
        assert row.user_id == uid


async def test_manager_may_transcribe_and_the_chain_separates_the_two_people() -> None:
    """Roster people have no account; a manager types their paper report in."""
    author = await _person("roster@aar.local")
    manager = await _person("opr@aar.local", role=Role.MANAGER)
    case_id, stub_id = await _stub_for(author)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        tok = await _token(c, "opr@aar.local")
        r = await c.post(
            f"/aar/cases/{case_id}/reports",
            headers=_auth(tok),
            json={"request_id": stub_id, "what_happened": "Записано зі слів"},
        )
    assert r.status_code == 201, r.text

    async with _Session() as s:
        entry = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.action == AuditAction.INDIVIDUAL_REPORT_SUBMITTED
                )
            )
        ).scalars().one()
    # Whose testimony it is, and who entered it, are different facts.
    assert entry.payload["originator_user_id"] == author
    assert entry.payload["transcribed_by"] == manager


async def test_self_submission_leaves_transcribed_by_empty() -> None:
    uid = await _person("crew@aar.local")
    case_id, stub_id = await _stub_for(uid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        tok = await _token(c, "crew@aar.local")
        await c.post(
            f"/aar/cases/{case_id}/reports",
            headers=_auth(tok),
            json={"request_id": stub_id, "what_happened": "Своїми словами"},
        )

    async with _Session() as s:
        entry = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.action == AuditAction.INDIVIDUAL_REPORT_SUBMITTED
                )
            )
        ).scalars().one()
    assert entry.payload["originator_user_id"] == uid
    assert entry.payload["transcribed_by"] is None


async def test_participant_cannot_author_a_free_form_report_as_someone_else() -> None:
    """The same forgery without a stub: POST {user_id: <colleague>}."""
    victim = await _person("victim@aar.local")
    await _person("attacker@aar.local")
    async with _Session() as s:
        case = AARCase(title="Кейс", trigger=TriggerType.MANUAL)
        s.add(case)
        await s.flush()
        case_id = case.id
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        tok = await _token(c, "attacker@aar.local")
        r = await c.post(
            f"/aar/cases/{case_id}/reports",
            headers=_auth(tok),
            json={"user_id": victim, "what_happened": "Не мої слова"},
        )
    assert r.status_code == 403, r.text


async def test_anonymous_self_submission_still_drops_the_author_from_the_row() -> None:
    uid = await _person("crew@aar.local")
    case_id, stub_id = await _stub_for(uid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        tok = await _token(c, "crew@aar.local")
        r = await c.post(
            f"/aar/cases/{case_id}/reports",
            headers=_auth(tok),
            json={"request_id": stub_id, "anonymous": True, "what_happened": "Тихо"},
        )
    assert r.status_code == 201, r.text

    async with _Session() as s:
        row = await s.get(IndividualReport, stub_id)
        assert row is not None
        assert row.user_id is None
        # Kept: the idempotency skip-set keys on it and it is the admin's only
        # identity handle. Redaction happens at the response boundary.
        assert row.requested_for_user_id == uid


async def test_transcriber_is_hidden_on_an_anonymous_report() -> None:
    """Who typed it up narrows who wrote it. Redact both, keep both in the chain."""
    author = await _person("roster@aar.local")
    await _person("opr@aar.local", role=Role.MANAGER)
    await _person("analyst@aar.local", role=Role.ANALYST)
    case_id, stub_id = await _stub_for(author)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        opr = await _token(c, "opr@aar.local")
        r = await c.post(
            f"/aar/cases/{case_id}/reports",
            headers=_auth(opr),
            json={"request_id": stub_id, "anonymous": True, "what_happened": "Тихо"},
        )
        assert r.status_code == 201, r.text

        seen = await c.get("/audit/log", headers=_auth(await _token(c, "analyst@aar.local")))
        assert seen.status_code == 200, seen.text

    entries = [
        e for e in seen.json()
        if e["action"] == AuditAction.INDIVIDUAL_REPORT_SUBMITTED.value
    ]
    assert entries, seen.text
    assert entries[0]["payload"]["transcribed_by"] is None
    assert entries[0]["payload"]["originator_user_id"] is None
    assert entries[0]["payload"]["originator_redacted"] is True

    # The chain itself still commits to both facts.
    async with _Session() as s:
        row = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.action == AuditAction.INDIVIDUAL_REPORT_SUBMITTED
                )
            )
        ).scalars().one()
    assert row.payload["originator_user_id"] == author
    assert row.payload["transcribed_by"] is not None
