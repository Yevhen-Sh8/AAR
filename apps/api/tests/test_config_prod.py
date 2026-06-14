"""Wave 4 — production config normalisation."""
from aar_api.core.config import Settings


def test_render_postgres_url_gets_asyncpg_driver() -> None:
    s = Settings(database_url="postgres://u:p@host:5432/db")
    assert s.database_url == "postgresql+asyncpg://u:p@host:5432/db"


def test_plain_postgresql_url_gets_asyncpg_driver() -> None:
    s = Settings(database_url="postgresql://u:p@host/db")
    assert s.database_url == "postgresql+asyncpg://u:p@host/db"


def test_already_async_url_unchanged() -> None:
    url = "postgresql+asyncpg://u:p@host/db"
    assert Settings(database_url=url).database_url == url


def test_sqlite_url_unchanged() -> None:
    url = "sqlite+aiosqlite:///:memory:"
    assert Settings(database_url=url).database_url == url


def test_sslmode_query_stripped_for_asyncpg() -> None:
    s = Settings(database_url="postgresql://u:p@host/db?sslmode=require")
    assert s.database_url == "postgresql+asyncpg://u:p@host/db"


def test_cors_origin_list_splits_and_trims() -> None:
    s = Settings(cors_origins="https://a.com, https://b.com ,")
    assert s.cors_origin_list == ["https://a.com", "https://b.com"]


def test_cors_wildcard_parsed() -> None:
    s = Settings(cors_origins="*")
    assert s.cors_origin_list == ["*"]


def test_cors_preflight_allows_origin() -> None:
    """The running app (default test config) answers a CORS preflight with an
    Access-Control-Allow-Origin header — proves the middleware is wired."""
    from starlette.testclient import TestClient

    from aar_api.main import app

    client = TestClient(app)
    r = client.options(
        "/events",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code in (200, 204)
    assert "access-control-allow-origin" in {k.lower() for k in r.headers}
