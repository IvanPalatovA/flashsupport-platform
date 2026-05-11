from fastapi.testclient import TestClient

from main import app
from routers import get_inference_service


class FakeInferenceService:
    def queue_depth(self) -> int:
        return 0


def test_health_endpoint_returns_ok() -> None:
    app.dependency_overrides[get_inference_service] = lambda: FakeInferenceService()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "queue_depth": 0}

    app.dependency_overrides.clear()
