from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from domain import (
	AccessDecisionEntity,
	ActionResultEntity,
	ChatStatus,
	DeliveryTarget,
	MessageEntity,
	OperatorAction,
	RAGResultEntity,
	Role,
	SpecialistDecision,
	SpecialistReviewResultEntity,
	UserMessageResultEntity,
)
from infrastructure.config import Settings


class PersistencePort(Protocol):
	def save_message(self, message: MessageEntity) -> None:
		...

	def save_event(self, chat_id: str, event_type: str, payload: dict[str, object]) -> None:
		...

	def update_chat_status(self, chat_id: str, status: ChatStatus, actor_id: str, note: str | None) -> None:
		...

	def enqueue_operator_request(self, chat_id: str, sender_role: Role, sender_id: str, text: str) -> str | None:
		...

	def enqueue_specialist_review(self, chat_id: str, operator_id: str, note: str) -> str | None:
		...

	def finalize_specialist_review(
		self,
		queue_item_id: str,
		chat_id: str,
		specialist_id: str,
		decision: SpecialistDecision,
		comment: str | None,
	) -> None:
		...

	def request_knowledge_base_update(
		self,
		queue_item_id: str,
		chat_id: str,
		specialist_id: str,
		comment: str | None,
	) -> None:
		...


class RAGPort(Protocol):
	def search(self, query: str, top_k: int, user_token: str) -> list[RAGResultEntity]:
		...


class AccessDeniedError(PermissionError):
	pass


_ALLOWED_PAIRS: set[tuple[Role, Role]] = {
	(Role.anonymous_user, Role.system),
	(Role.registered_user, Role.system),
	(Role.anonymous_user, Role.operator),
	(Role.registered_user, Role.operator),
	(Role.operator, Role.anonymous_user),
	(Role.operator, Role.registered_user),
	(Role.operator, Role.specialist),
	(Role.specialist, Role.operator),
	(Role.system, Role.anonymous_user),
	(Role.system, Role.registered_user),
}
_UNAVAILABLE_CHAT_STATUSES = {ChatStatus.blocked, ChatStatus.closed}


class ChatOrchestratorService:
	def __init__(self, persistence: PersistencePort, rag_engine: RAGPort, settings: Settings) -> None:
		self._persistence = persistence
		self._rag_engine = rag_engine
		self._settings = settings

	def check_access(
		self,
		sender_role: Role,
		recipient_role: Role,
		chat_status: ChatStatus = ChatStatus.open,
	) -> AccessDecisionEntity:
		if chat_status in _UNAVAILABLE_CHAT_STATUSES:
			return AccessDecisionEntity(
				allowed=False,
				reason=f"chat is {chat_status.value}; messaging is not allowed",
			)

		if (sender_role, recipient_role) not in _ALLOWED_PAIRS:
			return AccessDecisionEntity(
				allowed=False,
				reason=(
					"message flow is not allowed for this role pair "
					f"({sender_role.value} -> {recipient_role.value})"
				),
			)

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
		user_access_token: str,
	) -> UserMessageResultEntity:
		resolved_chat_id = chat_id or f"chat-{uuid4()}"
		target_role = Role.operator if request_operator else Role.system
		decision = self.check_access(sender_role=sender_role, recipient_role=target_role)
		if not decision.allowed:
			raise AccessDeniedError(decision.reason)

		message = MessageEntity(
			chat_id=resolved_chat_id,
			sender_role=sender_role,
			sender_id=sender_id,
			text=text,
			recipient_role=target_role,
		)
		self._persistence.save_message(message)
		self._persistence.save_event(
			chat_id=resolved_chat_id,
			event_type="user_message_received",
			payload={"sender_role": sender_role.value, "request_operator": request_operator},
		)

		if request_operator:
			queue_item_id = self._persistence.enqueue_operator_request(
				chat_id=resolved_chat_id,
				sender_role=sender_role,
				sender_id=sender_id,
				text=text,
			)
			self._persistence.update_chat_status(
				chat_id=resolved_chat_id,
				status=ChatStatus.waiting_operator,
				actor_id=sender_id,
				note="user_requested_operator",
			)
			return UserMessageResultEntity(
				chat_id=resolved_chat_id,
				route=DeliveryTarget.operator_queue,
				chat_status=ChatStatus.waiting_operator,
				message="Message forwarded to operator queue",
				rag_results=[],
				queue_item_id=queue_item_id,
			)

		final_top_k = top_k if top_k is not None else self._settings.default_top_k
		rag_results = self._rag_engine.search(query=text, top_k=final_top_k, user_token=user_access_token)
		self._persistence.save_event(
			chat_id=resolved_chat_id,
			event_type="forwarded_to_rag_engine",
			payload={"top_k": final_top_k, "result_count": len(rag_results)},
		)
		return UserMessageResultEntity(
			chat_id=resolved_chat_id,
			route=DeliveryTarget.rag_engine,
			chat_status=ChatStatus.open,
			message="Message forwarded to RAG Engine",
			rag_results=rag_results,
		)

	def process_operator_message(
		self,
		*,
		chat_id: str,
		operator_id: str,
		recipient_role: Role,
		text: str,
	) -> ActionResultEntity:
		decision = self.check_access(sender_role=Role.operator, recipient_role=recipient_role)
		if not decision.allowed:
			raise AccessDeniedError(decision.reason)

		message = MessageEntity(
			chat_id=chat_id,
			sender_role=Role.operator,
			sender_id=operator_id,
			text=text,
			recipient_role=recipient_role,
		)
		self._persistence.save_message(message)
		self._persistence.update_chat_status(
			chat_id=chat_id,
			status=ChatStatus.in_progress_operator,
			actor_id=operator_id,
			note="operator_reply",
		)
		self._persistence.save_event(
			chat_id=chat_id,
			event_type="operator_replied",
			payload={"recipient_role": recipient_role.value},
		)
		return ActionResultEntity(
			chat_id=chat_id,
			chat_status=ChatStatus.in_progress_operator,
			message="Operator message accepted",
		)

	def process_operator_action(
		self,
		*,
		chat_id: str,
		operator_id: str,
		action: OperatorAction,
		note: str | None,
	) -> ActionResultEntity:
		if action == OperatorAction.close_chat:
			status = ChatStatus.closed
			message = "Chat closed by operator"
			queue_item_id = None
		elif action == OperatorAction.block_chat:
			status = ChatStatus.blocked
			message = "Chat blocked by operator"
			queue_item_id = None
		elif action == OperatorAction.resolve_chat:
			status = ChatStatus.resolved
			message = "Chat resolved by operator"
			queue_item_id = None
		else:
			status = ChatStatus.specialist_review
			summary = note or "operator marked request as new knowledge candidate"
			queue_item_id = self._persistence.enqueue_specialist_review(
				chat_id=chat_id,
				operator_id=operator_id,
				note=summary,
			)
			message = "Request sent to specialist review queue"

		self._persistence.update_chat_status(
			chat_id=chat_id,
			status=status,
			actor_id=operator_id,
			note=note,
		)
		self._persistence.save_event(
			chat_id=chat_id,
			event_type="operator_action",
			payload={"action": action.value, "note": note or ""},
		)
		return ActionResultEntity(
			chat_id=chat_id,
			chat_status=status,
			message=message,
			queue_item_id=queue_item_id,
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
		self._persistence.finalize_specialist_review(
			queue_item_id=queue_item_id,
			chat_id=chat_id,
			specialist_id=specialist_id,
			decision=decision,
			comment=comment,
		)

		knowledge_base_update_requested = decision == SpecialistDecision.approve
		if knowledge_base_update_requested:
			self._persistence.request_knowledge_base_update(
				queue_item_id=queue_item_id,
				chat_id=chat_id,
				specialist_id=specialist_id,
				comment=comment,
			)
			new_status = ChatStatus.resolved
			message = "Specialist approved request and knowledge update was requested"
		else:
			new_status = ChatStatus.in_progress_operator
			message = "Specialist rejected request; chat returned to operator"

		self._persistence.update_chat_status(
			chat_id=chat_id,
			status=new_status,
			actor_id=specialist_id,
			note=comment,
		)
		self._persistence.save_event(
			chat_id=chat_id,
			event_type="specialist_review_completed",
			payload={"decision": decision.value, "knowledge_base_update_requested": knowledge_base_update_requested},
		)
		return SpecialistReviewResultEntity(
			queue_item_id=queue_item_id,
			decision=decision,
			knowledge_base_update_requested=knowledge_base_update_requested,
			message=message,
		)