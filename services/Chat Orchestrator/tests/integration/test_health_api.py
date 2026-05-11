import os

from fastapi.testclient import TestClient

os.environ.setdefault("CHAT_ORCHESTRATOR_ENV", "dev")

from main import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}