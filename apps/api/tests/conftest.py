import os

os.environ.setdefault("AAR_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AAR_ENVIRONMENT", "development")

import pytest  # noqa: E402

import aar_api.models  # noqa: F401, E402  ensure all tables are registered
from aar_api.core.db import Base, _engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _db_schema():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
