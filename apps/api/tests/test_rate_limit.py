"""Wave 5 hardening — login rate limiting."""
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.config import get_settings
from aar_api.core.db import _engine
from aar_api.core.security import hash_password
from aar_api.main import app
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


async def test_login_blocked_after_too_many_attempts() -> None:
    await _make_admin()
    limit = get_settings().login_rate_limit_attempts
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(limit):
            r = await client.post(
                "/auth/login", json={"email": "admin@aar.local", "password": "wrong"}
            )
            assert r.status_code == 401

        blocked = await client.post(
            "/auth/login", json={"email": "admin@aar.local", "password": "wrong"}
        )
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

        # Even the CORRECT password is blocked once the limit is hit — the
        # protection is against the attempt rate, not the credential itself.
        still_blocked = await client.post(
            "/auth/login", json={"email": "admin@aar.local", "password": "secret"}
        )
        assert still_blocked.status_code == 429


async def test_rate_limit_is_per_client_key() -> None:
    """A different X-Forwarded-For is a different bucket."""
    await _make_admin()
    limit = get_settings().login_rate_limit_attempts
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(limit):
            await client.post(
                "/auth/login",
                json={"email": "admin@aar.local", "password": "wrong"},
                headers={"X-Forwarded-For": "1.1.1.1"},
            )
        blocked = await client.post(
            "/auth/login",
            json={"email": "admin@aar.local", "password": "wrong"},
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        assert blocked.status_code == 429

        # Different source IP → fresh bucket → still gets the normal 401.
        other = await client.post(
            "/auth/login",
            json={"email": "admin@aar.local", "password": "wrong"},
            headers={"X-Forwarded-For": "2.2.2.2"},
        )
        assert other.status_code == 401
