from domain import SearchResultEntity
from infrastructure.config import Settings
from services import SearchService


class FakeRepository:
    def __init__(self) -> None:
        self.last_top_k: int | None = None
        self.last_query_embedding: list[float] | None = None

    def search(self, query_embedding: list[float], top_k: int) -> list[SearchResultEntity]:
        self.last_query_embedding = query_embedding
        self.last_top_k = top_k
        return [
            SearchResultEntity(
                chunk_id=1,
                document_id=10,
                document_title="Doc",
                chunk_index=0,
                score=0.9,
                text="test",
            )
        ]


def test_search_service_uses_default_top_k_and_returns_results() -> None:
    repository = FakeRepository()
    service = SearchService(
        repository=repository,
        settings=Settings(
            app_name="rag-service",
            env="test",
            host="0.0.0.0",
            port=8080,
            log_level="INFO",
            database_url="postgresql+psycopg://user:pass@localhost:5432/test",
            default_top_k=3,
            vector_dimension=16,
            auth_public_key_path="config/keys/auth/public.pem",
            auth_token_issuer="flashsupport-auth-service",
            user_access_token_audience="flashsupport-services",
            clock_skew_seconds=10,
        ),
    )

    results = service.search(query="reset password")

    assert len(results) == 1
    assert repository.last_top_k == 3
    assert repository.last_query_embedding is not None
    assert len(repository.last_query_embedding) == 16
