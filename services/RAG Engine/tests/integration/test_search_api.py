from fastapi.testclient import TestClient

from domain import SearchResultEntity
from infrastructure.security import RequestIdentity
from main import app
from routers import get_search_service, require_request_identity


class FakeSearchService:
    def search(self, query: str, top_k: int | None = None) -> list[SearchResultEntity]:
        assert query
        final_top_k = top_k or 3
        return [
            SearchResultEntity(
                chunk_id=1,
                document_id=99,
                document_title="Password reset guide",
                chunk_index=0,
                score=0.91,
                text="Сбросьте пароль через личный кабинет",
            )
            for _ in range(final_top_k)
        ]


def test_search_endpoint_happy_path() -> None:
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

    response = client.post("/search", json={"query": "как сбросить пароль", "top_k": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "как сбросить пароль"
    assert payload["top_k"] == 2
    assert len(payload["results"]) == 2
    assert payload["results"][0]["document_title"] == "Password reset guide"

    app.dependency_overrides.clear()


def test_search_endpoint_validation_error() -> None:
    app.dependency_overrides[require_request_identity] = lambda: RequestIdentity(
        user_subject="user-1",
        user_login="user",
        user_role="registered_user",
        service_id="chat-orchestrator",
        user_token="user-token",
        service_token="service-token",
    )
    client = TestClient(app)

    response = client.post("/search", json={"query": "", "top_k": 0})

    assert response.status_code == 422

    app.dependency_overrides.clear()
