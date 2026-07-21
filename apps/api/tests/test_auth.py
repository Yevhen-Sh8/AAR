"""Wave 5 — authentication: login, /auth/me, and the production auth gate."""
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import aar_api.main as main_module
from aar_api.core.db import _engine
from aar_api.core.security import hash_password
from aar_api.main import _is_public, app
from aar_api.models.user import Role, User


async def _make_admin(email: str = "admin@aar.local", password: str = "secret") -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(
            User(
                email=email,
                full_name="Admin",
                hashed_password=hash_password(password),
                role=Role.ADMIN,
            )
        )
        await s.commit()


async def test_login_success_returns_token() -> None:
    await _make_admin()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/auth/login", json={"email": "admin@aar.local", "password": "secret"}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["expires_minutes"] > 0


async def test_login_wrong_password_401() -> None:
    await _make_admin()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/auth/login", json={"email": "admin@aar.local", "password": "nope"}
        )
        assert r.status_code == 401


async def test_login_is_case_insensitive_email() -> None:
    await _make_admin()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/auth/login", json={"email": "ADMIN@AAR.LOCAL", "password": "secret"}
        )
        assert r.status_code == 200


async def test_me_returns_current_user() -> None:
    await _make_admin()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tok = (
            await client.post(
                "/auth/login", json={"email": "admin@aar.local", "password": "secret"}
            )
        ).json()["access_token"]
        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "admin@aar.local"
        assert body["role"] == "admin"


async def test_me_without_token_401() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/auth/me")
        assert r.status_code == 401


def test_is_public_allows_login_health_and_root() -> None:
    assert _is_public("/")
    assert _is_public("/auth/login")
    assert _is_public("/health/live")
    assert _is_public("/api/health/ready")  # root_path-prefixed
    assert _is_public("/api/auth/login")
    assert _is_public("/docs")
    assert not _is_public("/events")
    assert not _is_public("/api/events")
    assert not _is_public("/reports/daily")


async def test_gate_blocks_unauthenticated_in_production() -> None:
    """With the gate enabled (production), a protected path needs a token."""
    await _make_admin()
    original = main_module.settings.environment
    main_module.settings.environment = "production"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # No token → blocked.
            blocked = await client.get("/dictionaries/operators")
            assert blocked.status_code == 401

            # Login is public even with the gate on.
            tok = (
                await client.post(
                    "/auth/login",
                    json={"email": "admin@aar.local", "password": "secret"},
                )
            ).json()["access_token"]

            # With the token → allowed through the gate.
            ok = await client.get(
                "/dictionaries/operators",
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert ok.status_code == 200
    finally:
        main_module.settings.environment = original
