"""Wave 5 fix — admin seeding must upsert, not create-once.

Regression guard for the bug where changing AAR_ADMIN_PASSWORD in the hosting
dashboard had no effect after the first successful boot (seed skipped
existing users entirely, so the password was frozen forever).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.config import get_settings
from aar_api.core.db import _engine
from aar_api.core.security import verify_password
from aar_api.models.user import User
from aar_api.scripts.seed import _seed_admin


async def test_seed_admin_creates_when_absent(monkeypatch) -> None:
    monkeypatch.setenv("AAR_ADMIN_EMAIL", "admin@aar.local")
    monkeypatch.setenv("AAR_ADMIN_PASSWORD", "first-pass")
    get_settings.cache_clear()
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        await _seed_admin(s)
        await s.commit()
    async with Session() as s:
        user = await s.scalar(select(User).where(User.email == "admin@aar.local"))
        assert user is not None
        assert verify_password("first-pass", user.hashed_password)
    get_settings.cache_clear()


async def test_seed_admin_syncs_password_on_rerun(monkeypatch) -> None:
    """Simulates: user changes AAR_ADMIN_PASSWORD in Render → redeploy →
    seed runs again → the SAME admin row must pick up the new password."""
    monkeypatch.setenv("AAR_ADMIN_EMAIL", "admin@aar.local")
    monkeypatch.setenv("AAR_ADMIN_PASSWORD", "old-pass")
    get_settings.cache_clear()
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        await _seed_admin(s)
        await s.commit()

    monkeypatch.setenv("AAR_ADMIN_PASSWORD", "new-pass")
    get_settings.cache_clear()
    async with Session() as s:
        await _seed_admin(s)
        await s.commit()

    async with Session() as s:
        user = await s.scalar(select(User).where(User.email == "admin@aar.local"))
        assert user is not None
        assert verify_password("new-pass", user.hashed_password)
        assert not verify_password("old-pass", user.hashed_password)
    get_settings.cache_clear()
