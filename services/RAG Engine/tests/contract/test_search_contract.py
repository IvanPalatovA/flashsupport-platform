from fastapi.testclient import TestClient

from domain import SearchResultEntity
from main import app
from models import SearchResponse
from routers import get_search_service


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
    client = TestClient(app)

    response = client.post("/search", json={"query": "reset password", "top_k": 1})

    assert response.status_code == 200
    SearchResponse.model_validate(response.json())

    app.dependency_overrides.clear()
