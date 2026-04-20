from fastapi.testclient import TestClient

from domain import SearchResultEntity
from infrastructure.security import RequestIdentity
from main import app
from models import SearchResponse
from routers import get_search_service, require_request_identity


class FakeSearchService:
    def search(self, query: str, top_k: int | None = None) -> list[SearchResultEntity]:
        return [
            SearchResultEntity(
                chunk_id=1,
                document_id=2,
                document_title="Password reset guide",
                chunk_index=0,
                score=0.91,
                text="...",
            )
        ]


def test_search_response_contract() -> None:
    app.dependency_overrides[get_search_service] = lambda: FakeSearchService()
    app.dependency_overrides[require_request_identity] = lambda: RequestIdentity(
        user_subject="user-1",
        user_login="user",
        user_role="registered_user",
        service_id="chat-orchestrator",
        user_token="user-token",
        service_token="service-token",
    )
    client = TestClient(app)

    response = client.post("/search", json={"query": "reset password", "top_k": 1})

    assert response.status_code == 200
    SearchResponse.model_validate(response.json())

    app.dependency_overrides.clear()
