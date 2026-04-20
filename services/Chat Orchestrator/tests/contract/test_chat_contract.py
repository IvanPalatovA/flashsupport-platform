import os

from fastapi.testclient import TestClient

os.environ.setdefault("CHAT_ORCHESTRATOR_ENV", "dev")

from domain import ChatStatus, DeliveryTarget, RAGResultEntity, SpecialistDecision
from main import app
from models import AccessCheckResponse, ActionResponse, SpecialistReviewResponse, UserMessageResponse
from routes import get_orchestrator_service


class FakeService:
    def check_access(self, sender_role: object, recipient_role: object, chat_status: object) -> AccessCheckResponse:
        _ = sender_role
        _ = recipient_role
        _ = chat_status
        return AccessCheckResponse(allowed=True, reason="allowed")

    def process_user_message(
        self,
        *,
        chat_id: str | None,
        sender_id: str,
        sender_role: object,
        text: str,
        request_operator: bool,
        top_k: int | None,
    ) -> object:
        _ = chat_id
        _ = sender_id
        _ = sender_role
        _ = text
        _ = request_operator
        _ = top_k

        class Result:
            chat_id = "chat-1"
            route = DeliveryTarget.rag_engine
            chat_status = ChatStatus.open
            message = "Forwarded"
            queue_item_id = None
            rag_results = [
                RAGResultEntity(
                    chunk_id=1,
                    document_id=2,
                    document_title="doc",
                    chunk_index=0,
                    score=0.5,
                    text="snippet",
                )
            ]

        return Result()

    def process_operator_message(self, *, chat_id: str, operator_id: str, recipient_role: object, text: str) -> object:
        _ = chat_id
        _ = operator_id
        _ = recipient_role
        _ = text

        class Result:
            chat_id = "chat-1"
            chat_status = ChatStatus.in_progress_operator
            message = "Operator reply accepted"
            queue_item_id = None

        return Result()

    def process_operator_action(self, *, chat_id: str, operator_id: str, action: object, note: str | None) -> object:
        _ = chat_id
        _ = operator_id
        _ = action
        _ = note

        class Result:
            chat_id = "chat-1"
            chat_status = ChatStatus.closed
            message = "Chat closed"
            queue_item_id = None

        return Result()

    def process_specialist_review(
        self,
        *,
        queue_item_id: str,
        chat_id: str,
        specialist_id: str,
        decision: object,
        comment: str | None,
    ) -> object:
        _ = queue_item_id
        _ = chat_id
        _ = specialist_id
        _ = decision
        _ = comment

        class Result:
            queue_item_id = "q-1"
            decision = SpecialistDecision.approve
            knowledge_base_update_requested = True
            message = "Approved"

        return Result()


def test_user_message_response_contract() -> None:
    app.dependency_overrides[get_orchestrator_service] = lambda: FakeService()
    client = TestClient(app)

    response = client.post(
        "/messages/user",
        json={
            "sender_id": "user-1",
            "sender_role": "registered_user",
            "text": "reset password",
        },
    )

    assert response.status_code == 200
    UserMessageResponse.model_validate(response.json())

    app.dependency_overrides.clear()


def test_operator_action_response_contract() -> None:
    app.dependency_overrides[get_orchestrator_service] = lambda: FakeService()
    client = TestClient(app)

    response = client.post(
        "/operator/actions",
        json={
            "chat_id": "chat-1",
            "operator_id": "op-1",
            "action": "close_chat",
        },
    )

    assert response.status_code == 200
    ActionResponse.model_validate(response.json())

    app.dependency_overrides.clear()


def test_specialist_review_response_contract() -> None:
    app.dependency_overrides[get_orchestrator_service] = lambda: FakeService()
    client = TestClient(app)

    response = client.post(
        "/specialist/reviews",
        json={
            "queue_item_id": "queue-1",
            "chat_id": "chat-1",
            "specialist_id": "spec-1",
            "decision": "approve",
        },
    )

    assert response.status_code == 200
    SpecialistReviewResponse.model_validate(response.json())

    app.dependency_overrides.clear()


def test_access_check_response_contract() -> None:
    app.dependency_overrides[get_orchestrator_service] = lambda: FakeService()
    client = TestClient(app)

    response = client.post(
        "/access/check",
        json={
            "sender_role": "registered_user",
            "recipient_role": "operator",
            "chat_status": "open",
        },
    )

    assert response.status_code == 200
    AccessCheckResponse.model_validate(response.json())

    app.dependency_overrides.clear()