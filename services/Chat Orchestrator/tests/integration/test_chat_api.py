import os

from fastapi.testclient import TestClient

os.environ.setdefault("CHAT_ORCHESTRATOR_ENV", "dev")

from domain import (
    AccessDecisionEntity,
    ActionResultEntity,
    ChatStatus,
    DeliveryTarget,
    RAGResultEntity,
    Role,
    SpecialistDecision,
    SpecialistReviewResultEntity,
    UserMessageResultEntity,
)
from main import app
from routes import get_orchestrator_service


class FakeService:
    def check_access(self, sender_role: Role, recipient_role: Role, chat_status: ChatStatus) -> AccessDecisionEntity:
        _ = sender_role
        _ = recipient_role
        _ = chat_status
        return AccessDecisionEntity(allowed=True, reason="allowed")

    def process_user_message(
        self,
        *,
        chat_id: str | None,
        sender_id: str,
        sender_role: Role,
        text: str,
        request_operator: bool,
        top_k: int | None,
    ) -> UserMessageResultEntity:
        _ = chat_id
        _ = sender_id
        _ = sender_role
        _ = text
        _ = request_operator
        _ = top_k
        return UserMessageResultEntity(
            chat_id="chat-xyz",
            route=DeliveryTarget.rag_engine,
            chat_status=ChatStatus.open,
            message="Forwarded",
            rag_results=[
                RAGResultEntity(
                    chunk_id=1,
                    document_id=2,
                    document_title="Doc",
                    chunk_index=0,
                    score=0.8,
                    text="snippet",
                )
            ],
        )

    def process_operator_message(
        self,
        *,
        chat_id: str,
        operator_id: str,
        recipient_role: Role,
        text: str,
    ) -> ActionResultEntity:
        _ = chat_id
        _ = operator_id
        _ = recipient_role
        _ = text
        return ActionResultEntity(
            chat_id="chat-xyz",
            chat_status=ChatStatus.in_progress_operator,
            message="Operator accepted",
        )

    def process_operator_action(
        self,
        *,
        chat_id: str,
        operator_id: str,
        action: object,
        note: str | None,
    ) -> ActionResultEntity:
        _ = chat_id
        _ = operator_id
        _ = action
        _ = note
        return ActionResultEntity(
            chat_id="chat-xyz",
            chat_status=ChatStatus.closed,
            message="Closed",
        )

    def process_specialist_review(
        self,
        *,
        queue_item_id: str,
        chat_id: str,
        specialist_id: str,
        decision: SpecialistDecision,
        comment: str | None,
    ) -> SpecialistReviewResultEntity:
        _ = queue_item_id
        _ = chat_id
        _ = specialist_id
        _ = decision
        _ = comment
        return SpecialistReviewResultEntity(
            queue_item_id="queue-1",
            decision=SpecialistDecision.approve,
            knowledge_base_update_requested=True,
            message="Approved",
        )


def test_user_message_endpoint_happy_path() -> None:
    app.dependency_overrides[get_orchestrator_service] = lambda: FakeService()
    client = TestClient(app)

    response = client.post(
        "/messages/user",
        json={
            "sender_id": "user-1",
            "sender_role": "registered_user",
            "text": "Cannot login",
            "request_operator": False,
            "top_k": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_id"] == "chat-xyz"
    assert payload["route"] == "rag_engine"
    assert payload["chat_status"] == "open"
    assert len(payload["rag_results"]) == 1

    app.dependency_overrides.clear()


def test_operator_action_endpoint_happy_path() -> None:
    app.dependency_overrides[get_orchestrator_service] = lambda: FakeService()
    client = TestClient(app)

    response = client.post(
        "/operator/actions",
        json={
            "chat_id": "chat-xyz",
            "operator_id": "op-1",
            "action": "close_chat",
            "note": "Done",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_status"] == "closed"
    assert payload["message"] == "Closed"

    app.dependency_overrides.clear()


def test_user_message_endpoint_validation_error() -> None:
    client = TestClient(app)

    response = client.post(
        "/messages/user",
        json={
            "sender_id": "user-1",
            "sender_role": "operator",
            "text": "",
        },
    )

    assert response.status_code == 422