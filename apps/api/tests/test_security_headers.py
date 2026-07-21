"""Wave 5 hardening — security response headers."""
from httpx import ASGITransport, AsyncClient

from aar_api.main import app


async def test_public_response_carries_security_headers() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health/live")
        assert r.status_code == 200
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "strict-transport-security" in r.headers
        assert r.headers["content-security-policy"].startswith("default-src 'self'")


async def test_docs_path_gets_relaxed_csp_for_swagger_cdn() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/docs")
        assert r.status_code == 200
        assert "cdn.jsdelivr.net" in r.headers["content-security-policy"]
