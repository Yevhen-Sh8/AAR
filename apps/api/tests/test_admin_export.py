"""Wave 5 hardening — browser-only admin backup export."""
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import aar_api.main as main_module
from aar_api.core.db import _engine
from aar_api.core.security import create_access_token
from aar_api.main import app
from aar_api.models.dictionaries import Operator
from aar_api.models.user import Role


async def test_export_backup_returns_downloadable_snapshot() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(Operator(code="E-01", name_uk="01"))
        await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/admin/export")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/json")
        assert "attachment" in r.headers["content-disposition"]
        body = r.json()
        assert "exported_at" in body
        assert "app_version" in body
        assert any(row["code"] == "E-01" for row in body["tables"]["operators"])
        # Never leak password hashes, even in an admin-only export.
        assert "hashed_password" not in json_str_keys(body)


def json_str_keys(obj: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        keys |= set(obj.keys())
        for v in obj.values():
            keys |= json_str_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            keys |= json_str_keys(v)
    return keys


async def test_export_backup_requires_admin_role_in_production() -> None:
    original = main_module.settings.environment
    main_module.settings.environment = "production"
    try:
        analyst_tok = create_access_token(
            subject="a@x.com", extra={"role": Role.ANALYST.value, "uid": 1}
        )
        admin_tok = create_access_token(
            subject="admin@x.com", extra={"role": Role.ADMIN.value, "uid": 2}
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            no_token = await client.get("/admin/export")
            assert no_token.status_code == 401  # blocked by the global gate first

            forbidden = await client.get(
                "/admin/export", headers={"Authorization": f"Bearer {analyst_tok}"}
            )
            assert forbidden.status_code == 403

            ok = await client.get(
                "/admin/export", headers={"Authorization": f"Bearer {admin_tok}"}
            )
            assert ok.status_code == 200
    finally:
        main_module.settings.environment = original
