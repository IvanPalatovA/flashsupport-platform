from fastapi.testclient import TestClient

from domain import InferenceResultEntity
from infrastructure.security import RequestIdentity
from main import app
from models import InferenceResponse
from routers import get_inference_service, require_request_identity


class FakeInferenceService:
    allowed_caller_service_ids = {"chat-orchestrator", "rag-service"}

    async def infer(
        self,
        *,
        request_id: str | None,
        instruction: str,
        contexts: list[object],
        temperature: float | None,
        top_p: float | None,
        max_tokens: int | None,
    ) -> tuple[str, InferenceResultEntity]:
        _ = instruction
        _ = contexts
        _ = temperature
        _ = top_p
        _ = max_tokens

        return request_id or "req-1", InferenceResultEntity(
            answer="Сбросьте пароль через личный кабинет",
            model="llama3.1:8b",
            queue_wait_ms=3,
            inference_ms=90,
        )

    def queue_depth(self) -> int:
        return 0


def test_inference_response_contract() -> None:
    app.dependency_overrides[get_inference_service] = lambda: FakeInferenceService()
    app.dependency_overrides[require_request_identity] = lambda: RequestIdentity(
        user_subject="user-1",
        user_login="user",
        user_role="registered_user",
        service_id="chat-orchestrator",
        user_token="user-token",
        service_token="service-token",
    )
    client = TestClient(app)

    response = client.post(
        "/inference",
        json={
            "instruction": "Как сбросить пароль?",
            "contexts": [
                {
                    "chunk_id": 1,
                    "document_id": 10,
                    "document_title": "Password reset guide",
                    "chunk_index": 0,
                    "score": 0.91,
                    "text": "...",
                }
            ],
        },
    )

    assert response.status_code == 200
    InferenceResponse.model_validate(response.json())

    app.dependency_overrides.clear()
