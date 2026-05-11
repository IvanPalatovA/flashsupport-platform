from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from domain import ChatStatus, MessageEntity, RAGResultEntity, Role, SpecialistDecision
from infrastructure.auth_client import AuthClientError, ServiceTokenProvider


class UpstreamServiceError(RuntimeError):
	pass


def _safe_json_object(response: httpx.Response) -> dict[str, Any]:
	if not response.content:
		return {}
	try:
		payload: Any = response.json()
	except ValueError:
		return {}
	if not isinstance(payload, dict):
		return {}
	return cast(dict[str, Any], payload)


class ChatPersistenceRepository:
	def __init__(self, session: Session) -> None:
		self._session = session

	def _ensure_chat_exists(self, chat_id: str) -> None:
		self._session.execute(
			text(
				"""
				INSERT INTO chats (chat_id)
				VALUES (:chat_id)
				ON CONFLICT (chat_id) DO NOTHING
				"""
			),
			{"chat_id": chat_id},
		)

	def save_message(self, message: MessageEntity) -> None:
		self._ensure_chat_exists(message.chat_id)
		self._session.execute(
			text(
				"""
				INSERT INTO chat_messages (
					message_id,
					chat_id,
					sender_role,
					sender_id,
					recipient_role,
					text,
					created_at
				)
				VALUES (
					:message_id,
					:chat_id,
					:sender_role,
					:sender_id,
					:recipient_role,
					:text,
					:created_at
				)
				ON CONFLICT (message_id) DO NOTHING
				"""
			),
			{
				"message_id": message.message_id,
				"chat_id": message.chat_id,
				"sender_role": message.sender_role.value,
				"sender_id": message.sender_id,
				"recipient_role": message.recipient_role.value,
				"text": message.text,
				"created_at": message.created_at,
			},
		)

	def save_event(self, chat_id: str, event_type: str, payload: dict[str, object]) -> None:
		self._ensure_chat_exists(chat_id)
		self._session.execute(
			text(
				"""
				INSERT INTO chat_events (chat_id, event_type, payload)
				VALUES (:chat_id, :event_type, CAST(:payload AS JSONB))
				"""
			),
			{"chat_id": chat_id, "event_type": event_type, "payload": json.dumps(payload)},
		)

	def update_chat_status(self, chat_id: str, status: ChatStatus, actor_id: str, note: str | None) -> None:
		self._ensure_chat_exists(chat_id)
		self._session.execute(
			text(
				"""
				INSERT INTO chats (chat_id, status, updated_by, note)
				VALUES (:chat_id, :status, :actor_id, :note)
				ON CONFLICT (chat_id)
				DO UPDATE SET
					status = EXCLUDED.status,
					updated_by = EXCLUDED.updated_by,
					note = EXCLUDED.note,
					updated_at = NOW()
				"""
			),
			{"chat_id": chat_id, "status": status.value, "actor_id": actor_id, "note": note},
		)
		self._session.execute(
			text(
				"""
				INSERT INTO chat_status_history (chat_id, status, actor_id, note)
				VALUES (:chat_id, :status, :actor_id, :note)
				"""
			),
			{"chat_id": chat_id, "status": status.value, "actor_id": actor_id, "note": note},
		)

	def enqueue_operator_request(self, chat_id: str, sender_role: Role, sender_id: str, text: str) -> str | None:
		self._ensure_chat_exists(chat_id)
		queue_item_id = f"opq-{uuid4()}"
		self._session.execute(
			text(
				"""
				INSERT INTO operator_queue (queue_item_id, chat_id, sender_role, sender_id, text)
				VALUES (:queue_item_id, :chat_id, :sender_role, :sender_id, :text)
				"""
			),
			{
				"queue_item_id": queue_item_id,
				"chat_id": chat_id,
				"sender_role": sender_role.value,
				"sender_id": sender_id,
				"text": text,
			},
		)
		return queue_item_id

	def enqueue_specialist_review(self, chat_id: str, operator_id: str, note: str) -> str | None:
		self._ensure_chat_exists(chat_id)
		queue_item_id = f"spq-{uuid4()}"
		self._session.execute(
			text(
				"""
				INSERT INTO specialist_queue (queue_item_id, chat_id, operator_id, note)
				VALUES (:queue_item_id, :chat_id, :operator_id, :note)
				"""
			),
			{
				"queue_item_id": queue_item_id,
				"chat_id": chat_id,
				"operator_id": operator_id,
				"note": note,
			},
		)
		return queue_item_id

	def finalize_specialist_review(
		self,
		queue_item_id: str,
		chat_id: str,
		specialist_id: str,
		decision: SpecialistDecision,
		comment: str | None,
	) -> None:
		self._ensure_chat_exists(chat_id)
		self._session.execute(
			text(
				"""
				UPDATE specialist_queue
				SET
					status = 'reviewed',
					decision = :decision,
					specialist_id = :specialist_id,
					comment = :comment,
					reviewed_at = NOW()
				WHERE queue_item_id = :queue_item_id AND chat_id = :chat_id
				"""
			),
			{
				"queue_item_id": queue_item_id,
				"chat_id": chat_id,
				"specialist_id": specialist_id,
				"decision": decision.value,
				"comment": comment,
			},
		)

	def request_knowledge_base_update(
		self,
		queue_item_id: str,
		chat_id: str,
		specialist_id: str,
		comment: str | None,
	) -> None:
		self._ensure_chat_exists(chat_id)
		self._session.execute(
			text(
				"""
				INSERT INTO knowledge_base_updates (queue_item_id, chat_id, specialist_id, comment)
				VALUES (:queue_item_id, :chat_id, :specialist_id, :comment)
				"""
			),
			{
				"queue_item_id": queue_item_id,
				"chat_id": chat_id,
				"specialist_id": specialist_id,
				"comment": comment,
			},
		)


class RagEngineRepository:
	def __init__(self, base_url: str, timeout_seconds: float, service_token_provider: ServiceTokenProvider) -> None:
		self._base_url = base_url.rstrip("/")
		self._timeout_seconds = timeout_seconds
		self._service_token_provider = service_token_provider

	def search(self, query: str, top_k: int, user_token: str) -> list[RAGResultEntity]:
		url = f"{self._base_url}/search"
		try:
			service_token = self._service_token_provider.get_service_access_token()
			response = httpx.post(
				url,
				json={"query": query, "top_k": top_k},
				headers={
					"Authorization": f"Bearer {user_token}",
					"X-Service-Authorization": f"Bearer {service_token}",
					"X-Service-Name": self._service_token_provider.service_id,
				},
				timeout=self._timeout_seconds,
			)
			response.raise_for_status()
		except AuthClientError as error:
			raise UpstreamServiceError("RAG Engine request failed: /search (service token error)") from error
		except httpx.HTTPError as error:
			detail = "RAG Engine request failed: /search"
			if isinstance(error, httpx.HTTPStatusError):
				payload = _safe_json_object(error.response)
				upstream_detail = payload.get("detail")
				if isinstance(upstream_detail, str) and upstream_detail.strip() != "":
					detail = f"{detail} ({error.response.status_code}: {upstream_detail.strip()})"
				else:
					detail = f"{detail} ({error.response.status_code})"
			elif str(error).strip() != "":
				detail = f"{detail} ({str(error).strip()})"
			raise UpstreamServiceError(detail) from error

		data = _safe_json_object(response)
		raw_results_obj = data.get("results")
		if not isinstance(raw_results_obj, list):
			return []
		raw_results = cast(list[Any], raw_results_obj)

		results: list[RAGResultEntity] = []
		for raw_item in raw_results:
			if not isinstance(raw_item, dict):
				continue
			item = cast(dict[str, Any], raw_item)
			if "text" not in item:
				continue
			results.append(
				RAGResultEntity(
					chunk_id=item.get("chunk_id", ""),
					document_id=item.get("document_id", ""),
					document_title=str(item.get("document_title", "")),
					chunk_index=int(item.get("chunk_index", 0)),
					score=float(item.get("score", 0.0)),
					text=str(item.get("text", "")),
				)
			)
		return results
