from __future__ import annotations

from typing import Any, cast

import httpx

from domain import ChatStatus, MessageEntity, RAGResultEntity, Role, SpecialistDecision


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


class PersistenceApiRepository:
	def __init__(self, base_url: str, timeout_seconds: float) -> None:
		self._base_url = base_url.rstrip("/")
		self._timeout_seconds = timeout_seconds

	def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
		url = f"{self._base_url}{path}"
		try:
			response = httpx.post(url, json=payload, timeout=self._timeout_seconds)
			response.raise_for_status()
			return _safe_json_object(response)
		except httpx.HTTPError as error:
			raise UpstreamServiceError(f"Persistence API request failed: {path}") from error

	def save_message(self, message: MessageEntity) -> None:
		self._post(
			"/v1/chats/messages",
			{
				"message_id": message.message_id,
				"chat_id": message.chat_id,
				"sender_role": message.sender_role.value,
				"sender_id": message.sender_id,
				"recipient_role": message.recipient_role.value,
				"text": message.text,
				"created_at": message.created_at.isoformat(),
			},
		)

	def save_event(self, chat_id: str, event_type: str, payload: dict[str, object]) -> None:
		self._post(
			"/v1/chats/events",
			{
				"chat_id": chat_id,
				"event_type": event_type,
				"payload": payload,
			},
		)

	def update_chat_status(self, chat_id: str, status: ChatStatus, actor_id: str, note: str | None) -> None:
		self._post(
			"/v1/chats/status",
			{
				"chat_id": chat_id,
				"status": status.value,
				"actor_id": actor_id,
				"note": note,
			},
		)

	def enqueue_operator_request(self, chat_id: str, sender_role: Role, sender_id: str, text: str) -> str | None:
		data = self._post(
			"/v1/queues/operator",
			{
				"chat_id": chat_id,
				"sender_role": sender_role.value,
				"sender_id": sender_id,
				"text": text,
			},
		)
		queue_item_id = data.get("queue_item_id")
		return str(queue_item_id) if queue_item_id is not None else None

	def enqueue_specialist_review(self, chat_id: str, operator_id: str, note: str) -> str | None:
		data = self._post(
			"/v1/queues/specialist",
			{
				"chat_id": chat_id,
				"operator_id": operator_id,
				"note": note,
			},
		)
		queue_item_id = data.get("queue_item_id")
		return str(queue_item_id) if queue_item_id is not None else None

	def finalize_specialist_review(
		self,
		queue_item_id: str,
		chat_id: str,
		specialist_id: str,
		decision: SpecialistDecision,
		comment: str | None,
	) -> None:
		self._post(
			"/v1/queues/specialist/review",
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
		self._post(
			"/v1/knowledge/updates",
			{
				"queue_item_id": queue_item_id,
				"chat_id": chat_id,
				"specialist_id": specialist_id,
				"comment": comment,
			},
		)


class RagEngineRepository:
	def __init__(self, base_url: str, timeout_seconds: float) -> None:
		self._base_url = base_url.rstrip("/")
		self._timeout_seconds = timeout_seconds

	def search(self, query: str, top_k: int) -> list[RAGResultEntity]:
		url = f"{self._base_url}/search"
		try:
			response = httpx.post(
				url,
				json={"query": query, "top_k": top_k},
				timeout=self._timeout_seconds,
			)
			response.raise_for_status()
		except httpx.HTTPError as error:
			raise UpstreamServiceError("RAG Engine request failed: /search") from error

		data = _safe_json_object(response)
		raw_results = data.get("results")
		if not isinstance(raw_results, list):
			return []

		results: list[RAGResultEntity] = []
		for raw_item in raw_results:
			if not isinstance(raw_item, dict):
				continue
			if "text" not in raw_item:
				continue
			results.append(
				RAGResultEntity(
					chunk_id=raw_item.get("chunk_id", ""),
					document_id=raw_item.get("document_id", ""),
					document_title=str(raw_item.get("document_title", "")),
					chunk_index=int(raw_item.get("chunk_index", 0)),
					score=float(raw_item.get("score", 0.0)),
					text=str(raw_item.get("text", "")),
				)
			)
		return results