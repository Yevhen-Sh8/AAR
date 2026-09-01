"""Wave 12 — the participant-facing surface and the author feedback loop.

The Parallax Debrief concept names ONE function as decisive: the author of an
observation must see what came of it — not «ваше зауваження прийнято» but
«через ваше зауваження змінено ось цю процедуру». Their modelling puts
submission at 14% instead of 68% without it, and a Level-2 system nobody
submits to is just a metrics dashboard.
"""
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.core.security import hash_password
from aar_api.main import app
from aar_api.models.aar import (
    AARCase,
    IndividualReport,
    Recommendation,
    RecommendationStatus,
    TriggerType,
)
from aar_api.models.user import Role, User

_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def _seed_person(email: str = "crew@aar.local") -> int:
    async with _Session() as s:
        u = User(
            email=email,
            full_name="Оператор",
            hashed_password=hash_password("secret12"),
            role=Role.PARTICIPANT,
        )
        s.add(u)
        await s.flush()
        uid = u.id
        await s.commit()
    return uid


async def _token(client: AsyncClient, email: str = "crew@aar.local") -> str:
    r = await client.post("/auth/login", json={"email": email, "password": "secret12"})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


async def _case_with_my_report(
    uid: int, *, anonymous: bool = False, **case_fields
) -> tuple[int, int]:
    async with _Session() as s:
        case = AARCase(title="Втрата над ціллю", trigger=TriggerType.MANUAL, **case_fields)
        s.add(case)
        await s.flush()
        rep = IndividualReport(
            case_id=case.id,
            requested_for_user_id=uid,
            user_id=None if anonymous else uid,
            anonymous=anonymous,
            requested_at=datetime.now(UTC),
            submitted_at=datetime.now(UTC),
            what_happened="Зник звʼязок на підльоті",
        )
        s.add(rep)
        await s.flush()
        ids = (case.id, rep.id)
        await s.commit()
    return ids


async def test_my_requests_show_what_is_asked_of_me() -> None:
    """Before this, a webhook said "submit a report" and named no case."""
    uid = await _seed_person()
    async with _Session() as s:
        case = AARCase(title="Кейс із запитом", trigger=TriggerType.MANUAL)
        s.add(case)
        await s.flush()
        s.add(
            IndividualReport(
                case_id=case.id,
                requested_for_user_id=uid,
                requested_at=datetime.now(UTC),
            )
        )
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tok = await _token(client)
        r = await client.get(
            "/aar/my-report-requests", headers={"Authorization": f"Bearer {tok}"}
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["case_title"] == "Кейс із запитом"
        assert rows[0]["submitted_at"] is None


async def test_personal_endpoints_require_identity() -> None:
    """require_role would short-circuit to ADMIN in dev and leak everyone's."""
    await _seed_person()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/aar/my-report-requests", "/aar/my-observations"):
            r = await client.get(path)
            assert r.status_code == 401, f"{path}: {r.text}"


async def test_i_do_not_see_other_peoples_requests() -> None:
    mine = await _seed_person("mine@aar.local")
    other = await _seed_person("other@aar.local")
    async with _Session() as s:
        case = AARCase(title="Чужий кейс", trigger=TriggerType.MANUAL)
        s.add(case)
        await s.flush()
        s.add_all([
            IndividualReport(case_id=case.id, requested_for_user_id=other,
                             requested_at=datetime.now(UTC)),
            IndividualReport(case_id=case.id, requested_for_user_id=mine,
                             requested_at=datetime.now(UTC)),
        ])
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tok = await _token(client, "mine@aar.local")
        rows = (
            await client.get(
                "/aar/my-report-requests", headers={"Authorization": f"Bearer {tok}"}
            )
        ).json()
        assert len(rows) == 1, "must return only the caller's own requests"


async def test_outcome_names_the_consequence_not_the_receipt() -> None:
    """The whole point: «змінено процедуру», never «звіт прийнято»."""
    uid = await _seed_person()
    case_id, _ = await _case_with_my_report(
        uid, lesson_identified="Перевіряти канал перед вильотом"
    )
    async with _Session() as s:
        s.add(
            Recommendation(
                case_id=case_id,
                text="Ввести передпольотну перевірку каналу",
                status=RecommendationStatus.VALIDATED,
                auto_validated_at=datetime.now(UTC),
            )
        )
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tok = await _token(client)
        rows = (
            await client.get(
                "/aar/my-observations", headers={"Authorization": f"Bearer {tok}"}
            )
        ).json()

    assert len(rows) == 1
    row = rows[0]
    assert "підтверджена даними" in row["outcome_uk"]
    assert row["lesson_identified"] == "Перевіряти канал перед вильотом"
    assert row["recommendations"][0]["text"] == "Ввести передпольотну перевірку каналу"
    assert row["recommendations"][0]["status"] == "validated"


async def test_outcome_is_honest_while_nothing_has_happened_yet() -> None:
    """No recommendation yet must not read as success."""
    uid = await _seed_person()
    await _case_with_my_report(uid)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tok = await _token(client)
        rows = (
            await client.get(
                "/aar/my-observations", headers={"Authorization": f"Bearer {tok}"}
            )
        ).json()
    assert rows[0]["outcome_uk"].startswith("Звіт отримано")
    assert rows[0]["recommendations"] == []


async def test_anonymous_stub_report_still_reaches_its_author() -> None:
    """Anonymity hides the author from OTHERS, not from themselves.

    The stub keeps requested_for_user_id (redacted for everyone else by
    services/redaction.py), so the author keeps the feedback loop.
    """
    uid = await _seed_person()
    await _case_with_my_report(uid, anonymous=True, lesson_identified="Урок")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tok = await _token(client)
        rows = (
            await client.get(
                "/aar/my-observations", headers={"Authorization": f"Bearer {tok}"}
            )
        ).json()
    assert len(rows) == 1
    assert rows[0]["anonymous"] is True
    assert rows[0]["lesson_identified"] == "Урок"


async def test_unsubmitted_requests_are_not_observations() -> None:
    """"What came of it" is meaningless before anything was said."""
    uid = await _seed_person()
    async with _Session() as s:
        case = AARCase(title="Ще не подано", trigger=TriggerType.MANUAL)
        s.add(case)
        await s.flush()
        s.add(
            IndividualReport(
                case_id=case.id,
                requested_for_user_id=uid,
                requested_at=datetime.now(UTC),
            )
        )
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tok = await _token(client)
        obs = (
            await client.get(
                "/aar/my-observations", headers={"Authorization": f"Bearer {tok}"}
            )
        ).json()
        reqs = (
            await client.get(
                "/aar/my-report-requests", headers={"Authorization": f"Bearer {tok}"}
            )
        ).json()
    assert obs == [], "an unsubmitted request has no outcome to report"
    assert len(reqs) == 1, "but it must still appear as something asked of me"
