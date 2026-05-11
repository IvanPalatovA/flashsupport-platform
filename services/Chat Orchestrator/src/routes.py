from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, status

from infrastructure.auth_client import ServiceTokenProvider
from infrastructure.config import Settings, get_settings
from infrastructure.repositories import PersistenceApiRepository, RagEngineRepository, UpstreamServiceError
from infrastructure.security import AuthTokenError, AuthTokenVerifier, RequestIdentity
from models import (
	AccessCheckRequest,
	AccessCheckResponse,
	ActionResponse,
	HealthResponse,
	OperatorActionRequest,
	OperatorMessageRequest,
	RAGResult,
	SpecialistReviewRequest,
	SpecialistReviewResponse,
	UserMessageRequest,
	UserMessageResponse,
)
from service import AccessDeniedError, ChatOrchestratorService

router = APIRouter()


@lru_cache(maxsize=1)
def get_service_token_provider() -> ServiceTokenProvider:
	return ServiceTokenProvider(get_settings())


@lru_cache(maxsize=1)
def get_token_verifier() -> AuthTokenVerifier:
	return AuthTokenVerifier(get_settings())


def require_request_identity(
	authorization: str = Header(..., alias="Authorization"),
	service_authorization: str = Header(..., alias="X-Service-Authorization"),
	service_name: str = Header(..., alias="X-Service-Name"),
	settings: Settings = Depends(get_settings),
) -> RequestIdentity:
	verifier = get_token_verifier()
	try:
		return verifier.verify_request(
			authorization_header=authorization,
			service_authorization_header=service_authorization,
			service_name_header=service_name,
			expected_service_audience=settings.app_name,
		)
	except AuthTokenError as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error


def _enforce_actor_identity(identity: RequestIdentity, actor_id: str, required_role: str) -> None:
	if identity.user_subject != actor_id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="token subject does not match actor identifier",
		)
	if identity.user_role != required_role:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail=f"user role '{required_role}' is required",
		)


def get_orchestrator_service(
	settings: Settings = Depends(get_settings),
	token_provider: ServiceTokenProvider = Depends(get_service_token_provider),
) -> ChatOrchestratorService:
	persistence = PersistenceApiRepository(
		base_url=settings.persistence_api_url,
		timeout_seconds=settings.http_timeout_seconds,
	)
	rag_engine = RagEngineRepository(
		base_url=settings.rag_engine_url,
		timeout_seconds=settings.http_timeout_seconds,
		service_token_provider=token_provider,
	)
	return ChatOrchestratorService(
		persistence=persistence,
		rag_engine=rag_engine,
		settings=settings,
	)


def _map_error(error: Exception) -> HTTPException:
	if isinstance(error, AccessDeniedError):
		return HTTPException(status_code=403, detail=str(error))
	if isinstance(error, UpstreamServiceError):
		return HTTPException(status_code=502, detail=str(error))
	return HTTPException(status_code=500, detail="internal orchestrator error")


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
	return HealthResponse(status="ok")


@router.post("/access/check", response_model=AccessCheckResponse, tags=["access"])
def check_access(
	payload: AccessCheckRequest,
	_: RequestIdentity = Depends(require_request_identity),
	service: ChatOrchestratorService = Depends(get_orchestrator_service),
) -> AccessCheckResponse:
	decision = service.check_access(
		sender_role=payload.sender_role,
		recipient_role=payload.recipient_role,
		chat_status=payload.chat_status,
	)
	return AccessCheckResponse(allowed=decision.allowed, reason=decision.reason)


@router.post("/messages/user", response_model=UserMessageResponse, tags=["messages"])
def user_message(
	payload: UserMessageRequest,
	identity: RequestIdentity = Depends(require_request_identity),
	service: ChatOrchestratorService = Depends(get_orchestrator_service),
) -> UserMessageResponse:
	if identity.user_subject != payload.sender_id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="token subject must match sender_id",
		)
	if identity.user_role != payload.sender_role.value:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="token role must match sender_role",
		)

	try:
		result = service.process_user_message(
			chat_id=payload.chat_id,
			sender_id=payload.sender_id,
			sender_role=payload.sender_role,
			text=payload.text,
			request_operator=payload.request_operator,
			top_k=payload.top_k,
			user_access_token=identity.user_token,
		)
	except Exception as error:  # pragma: no cover - handled by tests through concrete errors
		raise _map_error(error) from error

	return UserMessageResponse(
		chat_id=result.chat_id,
		route=result.route.value,
		chat_status=result.chat_status.value,
		message=result.message,
		queue_item_id=result.queue_item_id,
		rag_results=[
			RAGResult(
				chunk_id=item.chunk_id,
				document_id=item.document_id,
				document_title=item.document_title,
				chunk_index=item.chunk_index,
				score=item.score,
				text=item.text,
			)
			for item in result.rag_results
		],
	)


@router.post("/messages/operator", response_model=ActionResponse, tags=["messages"])
def operator_message(
	payload: OperatorMessageRequest,
	identity: RequestIdentity = Depends(require_request_identity),
	service: ChatOrchestratorService = Depends(get_orchestrator_service),
) -> ActionResponse:
	_enforce_actor_identity(identity=identity, actor_id=payload.operator_id, required_role="operator")

	try:
		result = service.process_operator_message(
			chat_id=payload.chat_id,
			operator_id=payload.operator_id,
			recipient_role=payload.recipient_role,
			text=payload.text,
		)
	except Exception as error:  # pragma: no cover - handled by tests through concrete errors
		raise _map_error(error) from error

	return ActionResponse(
		chat_id=result.chat_id,
		chat_status=result.chat_status.value,
		message=result.message,
		queue_item_id=result.queue_item_id,
	)


@router.post("/operator/actions", response_model=ActionResponse, tags=["operator"])
def operator_action(
	payload: OperatorActionRequest,
	identity: RequestIdentity = Depends(require_request_identity),
	service: ChatOrchestratorService = Depends(get_orchestrator_service),
) -> ActionResponse:
	_enforce_actor_identity(identity=identity, actor_id=payload.operator_id, required_role="operator")

	try:
		result = service.process_operator_action(
			chat_id=payload.chat_id,
			operator_id=payload.operator_id,
			action=payload.action,
			note=payload.note,
		)
	except Exception as error:  # pragma: no cover - handled by tests through concrete errors
		raise _map_error(error) from error

	return ActionResponse(
		chat_id=result.chat_id,
		chat_status=result.chat_status.value,
		message=result.message,
		queue_item_id=result.queue_item_id,
	)


@router.post("/specialist/reviews", response_model=SpecialistReviewResponse, tags=["specialist"])
def specialist_review(
	payload: SpecialistReviewRequest,
	identity: RequestIdentity = Depends(require_request_identity),
	service: ChatOrchestratorService = Depends(get_orchestrator_service),
) -> SpecialistReviewResponse:
	_enforce_actor_identity(identity=identity, actor_id=payload.specialist_id, required_role="specialist")

	try:
		result = service.process_specialist_review(
			queue_item_id=payload.queue_item_id,
			chat_id=payload.chat_id,
			specialist_id=payload.specialist_id,
			decision=payload.decision,
			comment=payload.comment,
		)
	except Exception as error:  # pragma: no cover - handled by tests through concrete errors
		raise _map_error(error) from error

	return SpecialistReviewResponse(
		queue_item_id=result.queue_item_id,
		decision=result.decision.value,
		knowledge_base_update_requested=result.knowledge_base_update_requested,
		message=result.message,
	)