from fastapi.testclient import TestClient

from aar_api.main import app


def test_live() -> None:
    client = TestClient(app)
    r = client.get("/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
