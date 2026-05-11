from pydantic import BaseModel, Field, field_validator

from domain import ChatStatus, OperatorAction, Role, SpecialistDecision


class HealthResponse(BaseModel):
	status: str


class AccessCheckRequest(BaseModel):
	sender_role: Role
	recipient_role: Role
	chat_status: ChatStatus = ChatStatus.open


class AccessCheckResponse(BaseModel):
	allowed: bool
	reason: str


class UserMessageRequest(BaseModel):
	chat_id: str | None = Field(default=None, min_length=2, max_length=128)
	sender_id: str = Field(min_length=1, max_length=128)
	sender_role: Role
	text: str = Field(min_length=1, max_length=4000)
	request_operator: bool = False
	top_k: int | None = Field(default=None, ge=1, le=50)

	@field_validator("sender_role")
	@classmethod
	def validate_user_sender_role(cls, value: Role) -> Role:
		if value not in {Role.anonymous_user, Role.registered_user}:
			raise ValueError("sender_role must be anonymous_user or registered_user")
		return value


class RAGResult(BaseModel):
	chunk_id: int | str
	document_id: int | str
	document_title: str
	chunk_index: int
	score: float
	text: str


class UserMessageResponse(BaseModel):
	chat_id: str
	route: str
	chat_status: str
	message: str
	queue_item_id: str | None = None
	rag_results: list[RAGResult] = Field(default_factory=list)


class OperatorMessageRequest(BaseModel):
	chat_id: str = Field(min_length=2, max_length=128)
	operator_id: str = Field(min_length=1, max_length=128)
	recipient_role: Role
	text: str = Field(min_length=1, max_length=4000)

	@field_validator("recipient_role")
	@classmethod
	def validate_operator_recipient_role(cls, value: Role) -> Role:
		if value not in {Role.anonymous_user, Role.registered_user}:
			raise ValueError("recipient_role must be anonymous_user or registered_user")
		return value


class OperatorActionRequest(BaseModel):
	chat_id: str = Field(min_length=2, max_length=128)
	operator_id: str = Field(min_length=1, max_length=128)
	action: OperatorAction
	note: str | None = Field(default=None, max_length=1000)


class ActionResponse(BaseModel):
	chat_id: str
	chat_status: str
	message: str
	queue_item_id: str | None = None


class SpecialistReviewRequest(BaseModel):
	queue_item_id: str = Field(min_length=2, max_length=128)
	chat_id: str = Field(min_length=2, max_length=128)
	specialist_id: str = Field(min_length=1, max_length=128)
	decision: SpecialistDecision
	comment: str | None = Field(default=None, max_length=2000)


class SpecialistReviewResponse(BaseModel):
	queue_item_id: str
	decision: str
	knowledge_base_update_requested: bool
	message: str