"""Every state-changing endpoint must be reachable only by an entitled role.

These tests exist because the gates are INVISIBLE in the normal test run:
`require_role` short-circuits to ADMIN whenever the environment is
"development", which is also the test environment. So the other 130 tests pass
identically with or without a single gate in place. Here we mint real tokens for
real roles and assert the refusals, which is the only way this stays true.

The ordering being defended: reading a colleague's testimony already requires
ANALYST. Writing the official conclusion over it, moving the case along the NATO
cycle, closing it, or creating an outbound webhook must not require LESS.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import aar_api.main as main_module
from aar_api.core.config import get_settings
from aar_api.core.db import _engine
from aar_api.core.security import create_access_token
from aar_api.main import app
from aar_api.models.aar import AARCase, TriggerType
from aar_api.models.user import Role, User

_Session = async_sessionmaker(_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _production_env(monkeypatch: pytest.MonkeyPatch):
    """Run this module as production — otherwise the gates are unobservable.

    require_role() returns a synthetic ADMIN whenever the environment is
    "development", so in the default test env every assertion below would pass
    for the wrong reason. get_settings is lru_cached, hence the explicit clears.
    """
    monkeypatch.setenv("AAR_ENVIRONMENT", "production")
    get_settings.cache_clear()
    original = main_module.settings.environment
    main_module.settings.environment = "production"
    yield
    main_module.settings.environment = original
    get_settings.cache_clear()


def _token(role: Role, uid: int = 1) -> str:
    """A real signed token — require_role reads `role` out of the claims."""
    return create_access_token(subject=f"{role.value}@aar.local",
                               extra={"role": role.value, "uid": uid})


def _hdr(role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(role)}"}


async def _a_case() -> int:
    async with _Session() as s:
        c = AARCase(title="Кейс для перевірки прав", trigger=TriggerType.MANUAL)
        s.add(c)
        await s.flush()
        cid = c.id
        s.add(User(full_name="Учасник", role=Role.PARTICIPANT))
        await s.commit()
    return cid


async def test_participant_cannot_write_the_official_conclusion() -> None:
    """The inversion this fixes: reading testimony needed ANALYST, overwriting
    the conclusion needed nothing."""
    cid = await _a_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.patch(
            f"/aar/cases/{cid}",
            json={"lesson_identified": "переписано учасником"},
            headers=_hdr(Role.PARTICIPANT),
        )
        assert r.status_code == 403, r.text


async def test_participant_cannot_move_or_close_a_case() -> None:
    """A participant closing a case would take it out from under the
    auto-validation engine — the mechanism that proves the loop works."""
    cid = await _a_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        moved = await client.post(
            f"/aar/cases/{cid}/transition",
            json={"to": "analysed"},
            headers=_hdr(Role.PARTICIPANT),
        )
        assert moved.status_code == 403, moved.text

        closed = await client.post(
            f"/aar/cases/{cid}/close", headers=_hdr(Role.PARTICIPANT)
        )
        assert closed.status_code == 403, closed.text


async def test_analyst_may_analyse_but_not_close() -> None:
    """Analysis is analysis; closing a case is a command decision."""
    cid = await _a_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.patch(
            f"/aar/cases/{cid}",
            json={"analysis": "розбір причин"},
            headers=_hdr(Role.ANALYST),
        )
        assert ok.status_code == 200, ok.text

        refused = await client.post(
            f"/aar/cases/{cid}/close", headers=_hdr(Role.ANALYST)
        )
        assert refused.status_code == 403, refused.text


async def test_participant_cannot_touch_recommendations() -> None:
    """`validated` is settable through this endpoint, so an open PATCH meant the
    one metric that proves the loop works could be set by hand."""
    cid = await _a_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/aar/cases/{cid}/recommendations",
            json={"text": "щось зробити"},
            headers=_hdr(Role.PARTICIPANT),
        )
        assert created.status_code == 403, created.text


async def test_participant_cannot_run_the_trigger_engine() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/aar/run-triggers", headers=_hdr(Role.PARTICIPANT))
        assert r.status_code == 403, r.text


async def test_participant_may_still_submit_a_signal_but_not_review_one() -> None:
    """ADR-021: a low barrier to RAISE a warning is the point. Deciding what the
    unit does about someone else's warning is not."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/signals",
            json={"kind": "warning", "title": "РЕБ у секторі Б"},
            headers=_hdr(Role.PARTICIPANT),
        )
        assert created.status_code == 201, created.text
        sid = created.json()["id"]

        reviewed = await client.post(
            f"/signals/{sid}/review",
            json={"status": "accepted"},
            headers=_hdr(Role.PARTICIPANT),
        )
        assert reviewed.status_code == 403, reviewed.text

        converted = await client.post(
            f"/signals/{sid}/convert", headers=_hdr(Role.PARTICIPANT)
        )
        assert converted.status_code == 403, converted.text


async def test_only_integrator_or_admin_touches_outbound_channels() -> None:
    """Creating a webhook decides where operational data leaves the system, and
    the delivery log exposes target_url. The `integrator` role gated nothing
    anywhere in the codebase until now."""
    body = {
        "name": "test-hook",
        "kind": "generic",
        "target_url": "https://example.test/hook",
        "events": ["usage_event.created"],
        "active": True,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for role in (Role.PARTICIPANT, Role.ANALYST, Role.MANAGER):
            r = await client.post(
                "/integrations/subscriptions", json=body, headers=_hdr(role)
            )
            assert r.status_code == 403, f"{role.value}: {r.text}"
            log = await client.get("/integrations/deliveries", headers=_hdr(role))
            assert log.status_code == 403, f"{role.value} delivery log: {log.text}"

        allowed = await client.post(
            "/integrations/subscriptions", json=body, headers=_hdr(Role.INTEGRATOR)
        )
        assert allowed.status_code in (200, 201), allowed.text


async def test_participant_cannot_spend_the_llm_budget() -> None:
    cid = await _a_case()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/llm/cases/{cid}/draft-analysis", headers=_hdr(Role.PARTICIPANT)
        )
        assert r.status_code == 403, r.text
