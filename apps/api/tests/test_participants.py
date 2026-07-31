"""Wave 11 — flexible participants + the two report-flow security fixes.

The axiom under test: affiliation to an operator only SUGGESTS participants,
it never restricts who may be asked for testimony. The security fixes under
test: an anonymous report must not expose its submitter (BUG-1) and every
submission must reach the audit chain (BUG-2).
"""
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.core.security import hash_password
from aar_api.main import app
from aar_api.models.aar import AARCase, TriggerType
from aar_api.models.audit import AuditAction, AuditLog
from aar_api.models.dictionaries import Operator
from aar_api.models.user import ParticipantFunction, Role, User

_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def _seed() -> dict[str, int]:
    """Two operators, a person in each, and a case belonging to operator A."""
    async with _Session() as s:
        op_a = Operator(code="E-A", name_uk="Експлуатант A")
        op_b = Operator(code="E-B", name_uk="Експлуатант B")
        s.add_all([op_a, op_b])
        await s.flush()

        crew_a = User(
            full_name="Екіпаж A",
            role=Role.PARTICIPANT,
            operator_id=op_a.id,
            function=ParticipantFunction.CREW,
        )
        # Deliberately from the OTHER operator — the manufacturer rep whose
        # testimony is exactly what stops the crew being blamed by default.
        rep_b = User(
            full_name="Представник виробника B",
            role=Role.PARTICIPANT,
            operator_id=op_b.id,
            function=ParticipantFunction.MANUFACTURER,
        )
        admin = User(
            email="admin@aar.local",
            full_name="Admin",
            hashed_password=hash_password("secret"),
            role=Role.ADMIN,
        )
        s.add_all([crew_a, rep_b, admin])
        await s.flush()

        case = AARCase(title="Кейс A", operator_id=op_a.id, trigger=TriggerType.MANUAL)
        s.add(case)
        await s.flush()
        ids = {
            "op_a": op_a.id,
            "op_b": op_b.id,
            "crew_a": crew_a.id,
            "rep_b": rep_b.id,
            "case": case.id,
        }
        await s.commit()
    return ids


async def _admin_token(client: AsyncClient) -> str:
    r = await client.post(
        "/auth/login", json={"email": "admin@aar.local", "password": "secret"}
    )
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


# ---------------------------------------------------------------- the axiom

async def test_cross_operator_participant_is_allowed_and_only_flagged() -> None:
    """THE AXIOM: picking someone outside the case operator must NOT be a 4xx.

    It is recorded as a fact (off_roster) plus an advisory warning. If this
    test ever starts asserting a 4xx, the axiom has been violated.
    """
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/aar/cases/{ids['case']}/request-reports",
            json={"participants": [{"user_id": ids["rep_b"]}]},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["requested_count"] == 1
        assert ids["rep_b"] in body["off_roster_user_ids"]
        assert body["warnings"], "off-roster pick should warn, not block"


async def test_suggestions_rank_but_never_filter() -> None:
    """Affiliation may reorder the list; it must not remove anyone from it."""
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/people", params={"suggest_for_case_id": ids["case"]})
        assert r.status_code == 200, r.text
        returned = [p["id"] for p in r.json()]
        # The off-roster person is still present in the same list…
        assert ids["rep_b"] in returned
        # …and the affiliated one is ranked first.
        assert returned[0] == ids["crew_a"]


# ------------------------------------------------------- BUG-1: anonymity

async def test_anonymous_report_hides_submitter_from_non_admin() -> None:
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req = await client.post(
            f"/aar/cases/{ids['case']}/request-reports",
            json={"participants": [{"user_id": ids["crew_a"]}]},
        )
        assert req.status_code == 201, req.text
        stub_id = req.json()["pending_report_ids"][0]

        posted = await client.post(
            f"/aar/cases/{ids['case']}/reports",
            json={
                "request_id": stub_id,
                "user_id": ids["crew_a"],
                "anonymous": True,
                "what_happened": "Втрата над ціллю",
            },
        )
        assert posted.status_code in (200, 201), posted.text
        # No token at all => not privileged => must be redacted.
        assert posted.json()["user_id"] is None
        assert posted.json()["requested_for_user_id"] is None

        listed = (await client.get(f"/aar/cases/{ids['case']}/reports")).json()
        anon = [r for r in listed if r["anonymous"]]
        assert anon, "the anonymous report should still be listed"
        for row in anon:
            # BUG-1 was exactly this field leaking the submitter's identity.
            assert row["requested_for_user_id"] is None
            assert row["user_id"] is None


async def test_admin_can_still_see_originator() -> None:
    """Two-layer visibility (ADR-015): blame-free for peers, auditable for admin."""
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req = await client.post(
            f"/aar/cases/{ids['case']}/request-reports",
            json={"participants": [{"user_id": ids["crew_a"]}]},
        )
        stub_id = req.json()["pending_report_ids"][0]
        await client.post(
            f"/aar/cases/{ids['case']}/reports",
            json={
                "request_id": stub_id,
                "user_id": ids["crew_a"],
                "anonymous": True,
                "what_happened": "Втрата над ціллю",
            },
        )
        tok = await _admin_token(client)
        listed = (
            await client.get(
                f"/aar/cases/{ids['case']}/reports",
                headers={"Authorization": f"Bearer {tok}"},
            )
        ).json()
        anon = [r for r in listed if r["anonymous"]]
        assert anon and anon[0]["requested_for_user_id"] == ids["crew_a"]


# ----------------------------------------------------------- BUG-2: audit

async def test_submission_reaches_the_audit_chain_with_originator() -> None:
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req = await client.post(
            f"/aar/cases/{ids['case']}/request-reports",
            json={"participants": [{"user_id": ids["crew_a"]}]},
        )
        stub_id = req.json()["pending_report_ids"][0]
        await client.post(
            f"/aar/cases/{ids['case']}/reports",
            json={
                "request_id": stub_id,
                "user_id": ids["crew_a"],
                "anonymous": True,
                "what_happened": "Втрата над ціллю",
            },
        )

    async with _Session() as s:
        rows = list(
            await s.scalars(
                select(AuditLog).where(
                    AuditLog.action == AuditAction.INDIVIDUAL_REPORT_SUBMITTED
                )
            )
        )
    assert rows, "an anonymous submission must still be traceable in the chain"
    # The stored row keeps the true originator (the hash commits to it);
    # redaction happens only when serving /audit/log to non-admins.
    assert rows[-1].payload.get("originator_user_id") == ids["crew_a"]


async def test_audit_log_redacts_originator_for_non_admin() -> None:
    """Writing the originator into the chain must not just move the leak."""
    ids = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req = await client.post(
            f"/aar/cases/{ids['case']}/request-reports",
            json={"participants": [{"user_id": ids["crew_a"]}]},
        )
        stub_id = req.json()["pending_report_ids"][0]
        await client.post(
            f"/aar/cases/{ids['case']}/reports",
            json={
                "request_id": stub_id,
                "user_id": ids["crew_a"],
                "anonymous": True,
                "what_happened": "Втрата над ціллю",
            },
        )
        log = (await client.get("/audit/log")).json()
        entries = [
            e for e in log if e["action"] == AuditAction.INDIVIDUAL_REPORT_SUBMITTED.value
        ]
        assert entries
        for e in entries:
            assert e["payload"].get("originator_user_id") is None


# ------------------------------------------------- roster-only people/login

async def test_roster_only_person_cannot_log_in() -> None:
    """A person with no credentials is pickable but must never authenticate."""
    await _seed()
    async with _Session() as s:
        s.add(User(full_name="Обслуга без логіна", role=Role.PARTICIPANT))
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/auth/login", json={"email": "", "password": ""}
        )
        assert r.status_code in (401, 422)
