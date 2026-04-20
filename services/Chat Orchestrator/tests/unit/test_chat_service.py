from domain import (
    ChatStatus,
    OperatorAction,
    RAGResultEntity,
    Role,
    SpecialistDecision,
)
from infrastructure.config import Settings
from service import ChatOrchestratorService


class FakePersistence:
    def __init__(self) -> None:
        self.messages: list[object] = []
        self.events: list[tuple[str, str]] = []
        self.status_updates: list[tuple[str, ChatStatus]] = []
        self.knowledge_update_requests: int = 0

    def save_message(self, message: object) -> None:
        self.messages.append(message)

    def save_event(self, chat_id: str, event_type: str, payload: dict[str, object]) -> None:
        _ = payload
        self.events.append((chat_id, event_type))

    def update_chat_status(self, chat_id: str, status: ChatStatus, actor_id: str, note: str | None) -> None:
        _ = actor_id
        _ = note
        self.status_updates.append((chat_id, status))

    def enqueue_operator_request(self, chat_id: str, sender_role: Role, sender_id: str, text: str) -> str | None:
        _ = sender_role
        _ = sender_id
        _ = text
        return f"opq-{chat_id}"

    def enqueue_specialist_review(self, chat_id: str, operator_id: str, note: str) -> str | None:
        _ = operator_id
        _ = note
        return f"spq-{chat_id}"

    def finalize_specialist_review(
        self,
        queue_item_id: str,
        chat_id: str,
        specialist_id: str,
        decision: SpecialistDecision,
        comment: str | None,
    ) -> None:
        _ = queue_item_id
        _ = chat_id
        _ = specialist_id
        _ = decision
        _ = comment

    def request_knowledge_base_update(
        self,
        queue_item_id: str,
        chat_id: str,
        specialist_id: str,
        comment: str | None,
    ) -> None:
        _ = queue_item_id
        _ = chat_id
        _ = specialist_id
        _ = comment
        self.knowledge_update_requests += 1


class FakeRagEngine:
    def __init__(self) -> None:
        self.calls: int = 0

    def search(self, query: str, top_k: int) -> list[RAGResultEntity]:
        self.calls += 1
        _ = query
        return [
            RAGResultEntity(
                chunk_id=1,
                document_id=11,
                document_title="Password reset",
                chunk_index=0,
                score=0.95,
                text=f"result-{top_k}",
            )
        ]


def build_service() -> tuple[ChatOrchestratorService, FakePersistence, FakeRagEngine]:
    persistence = FakePersistence()
    rag_engine = FakeRagEngine()
    service = ChatOrchestratorService(
        persistence=persistence,
        rag_engine=rag_engine,
        settings=Settings(
            app_name="chat-orchestrator",
            env="test",
            host="0.0.0.0",
            port=8090,
            log_level="INFO",
            rag_engine_url="http://localhost:8080",
            persistence_api_url="http://localhost:8091",
            default_top_k=3,
            http_timeout_seconds=5,
        ),
    )
    return service, persistence, rag_engine


def test_user_message_goes_to_rag_engine_by_default() -> None:
    service, persistence, rag_engine = build_service()

    result = service.process_user_message(
        chat_id=None,
        sender_id="user-1",
        sender_role=Role.registered_user,
        text="I cannot reset my password",
        request_operator=False,
        top_k=None,
    )

    assert result.route.value == "rag_engine"
    assert result.chat_status == ChatStatus.open
    assert len(result.rag_results) == 1
    assert rag_engine.calls == 1
    assert len(persistence.messages) == 1


def test_user_message_can_be_escalated_to_operator_queue() -> None:
    service, persistence, rag_engine = build_service()

    result = service.process_user_message(
        chat_id="chat-100",
        sender_id="anon-42",
        sender_role=Role.anonymous_user,
        text="I need a human operator",
        request_operator=True,
        top_k=5,
    )

    assert result.route.value == "operator_queue"
    assert result.chat_status == ChatStatus.waiting_operator
    assert result.queue_item_id == "opq-chat-100"
    assert rag_engine.calls == 0
    assert persistence.status_updates[-1][1] == ChatStatus.waiting_operator


def test_operator_can_send_request_to_specialist_queue() -> None:
    service, persistence, _ = build_service()

    result = service.process_operator_action(
        chat_id="chat-200",
        operator_id="op-1",
        action=OperatorAction.send_to_specialist_queue,
        note="New product integration request",
    )

    assert result.chat_status == ChatStatus.specialist_review
    assert result.queue_item_id == "spq-chat-200"
    assert persistence.status_updates[-1][1] == ChatStatus.specialist_review


def test_specialist_approve_triggers_knowledge_update_request() -> None:
    service, persistence, _ = build_service()

    result = service.process_specialist_review(
        queue_item_id="spq-chat-300",
        chat_id="chat-300",
        specialist_id="spec-9",
        decision=SpecialistDecision.approve,
        comment="Approved",
    )

    assert result.knowledge_base_update_requested is True
    assert persistence.knowledge_update_requests == 1
    assert persistence.status_updates[-1][1] == ChatStatus.resolved