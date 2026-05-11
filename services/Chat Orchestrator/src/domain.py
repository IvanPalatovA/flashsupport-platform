from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class Role(str, Enum):
	anonymous_user = "anonymous_user"
	registered_user = "registered_user"
	operator = "operator"
	specialist = "specialist"
	system = "system"


class ChatStatus(str, Enum):
	open = "open"
	waiting_operator = "waiting_operator"
	in_progress_operator = "in_progress_operator"
	specialist_review = "specialist_review"
	resolved = "resolved"
	blocked = "blocked"
	closed = "closed"


class DeliveryTarget(str, Enum):
	rag_engine = "rag_engine"
	operator_queue = "operator_queue"
	specialist_queue = "specialist_queue"
	direct_user_reply = "direct_user_reply"
	chat_state_change = "chat_state_change"


class OperatorAction(str, Enum):
	close_chat = "close_chat"
	block_chat = "block_chat"
	resolve_chat = "resolve_chat"
	send_to_specialist_queue = "send_to_specialist_queue"


class SpecialistDecision(str, Enum):
	approve = "approve"
	reject = "reject"


@dataclass(slots=True)
class AccessDecisionEntity:
	allowed: bool
	reason: str


@dataclass(slots=True)
class RAGResultEntity:
	chunk_id: int | str
	document_id: int | str
	document_title: str
	chunk_index: int
	score: float
	text: str


@dataclass(slots=True)
class MessageEntity:
	chat_id: str
	sender_role: Role
	sender_id: str
	text: str
	recipient_role: Role
	message_id: str = field(default_factory=lambda: str(uuid4()))
	created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class UserMessageResultEntity:
	chat_id: str
	route: DeliveryTarget
	chat_status: ChatStatus
	message: str
	rag_results: list[RAGResultEntity]
	queue_item_id: str | None = None


@dataclass(slots=True)
class ActionResultEntity:
	chat_id: str
	chat_status: ChatStatus
	message: str
	queue_item_id: str | None = None


@dataclass(slots=True)
class SpecialistReviewResultEntity:
	queue_item_id: str
	decision: SpecialistDecision
	knowledge_base_update_requested: bool
	message: str