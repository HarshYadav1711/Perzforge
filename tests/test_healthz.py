from fastapi.testclient import TestClient

from api.main import app


def test_healthz_is_public_and_ok():
    client = TestClient(app)
    r = client.get("/api/v1/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
