from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint_returns_service_status() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}


def test_version_endpoint_returns_version() -> None:
    response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"
