from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, status

from domain import ContextChunkEntity
from infrastructure.auth_client import ServiceTokenProvider
from infrastructure.config import Settings, get_settings
from infrastructure.ollama_client import OllamaClient
from infrastructure.security import AuthTokenError, AuthTokenVerifier, RequestIdentity
from models import HealthResponse, InferenceRequest, InferenceResponse
from services import (
    InferenceBackendError,
    InferenceQueueFullError,
    InferenceTimeoutError,
    QueuedInferenceService,
    ServiceIdentityError,
)

router = APIRouter()


@lru_cache(maxsize=1)
def get_service_token_provider() -> ServiceTokenProvider:
    return ServiceTokenProvider(get_settings())


@lru_cache(maxsize=1)
def get_token_verifier() -> AuthTokenVerifier:
    return AuthTokenVerifier(get_settings())


@lru_cache(maxsize=1)
def get_inference_service() -> QueuedInferenceService:
    settings = get_settings()
    backend = OllamaClient(settings=settings)
    return QueuedInferenceService(
        settings=settings,
        backend=backend,
        service_identity_provider=get_service_token_provider(),
    )


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
            expected_service_audience=settings.incoming_service_token_audience,
        )
    except AuthTokenError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error


def _enforce_allowed_caller(identity: RequestIdentity, service: QueuedInferenceService) -> None:
    if identity.service_id not in service.allowed_caller_service_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="calling service is not allowed for LLM Runtime",
        )


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health(service: QueuedInferenceService = Depends(get_inference_service)) -> HealthResponse:
    return HealthResponse(status="ok", queue_depth=service.queue_depth())


@router.post("/inference", response_model=InferenceResponse, tags=["inference"])
async def inference(
    payload: InferenceRequest,
    identity: RequestIdentity = Depends(require_request_identity),
    service: QueuedInferenceService = Depends(get_inference_service),
) -> InferenceResponse:
    _enforce_allowed_caller(identity=identity, service=service)

    try:
        request_id, result = await service.infer(
            request_id=payload.request_id,
            instruction=payload.instruction,
            contexts=[
                ContextChunkEntity(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    document_title=item.document_title,
                    chunk_index=item.chunk_index,
                    score=item.score,
                    text=item.text,
                )
                for item in payload.contexts
            ],
            temperature=payload.temperature,
            top_p=payload.top_p,
            max_tokens=payload.max_tokens,
        )
    except InferenceQueueFullError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error
    except InferenceTimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(error)) from error
    except (InferenceBackendError, ServiceIdentityError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    return InferenceResponse(
        request_id=request_id,
        model=result.model,
        answer=result.answer,
        queue_wait_ms=result.queue_wait_ms,
        inference_ms=result.inference_ms,
    )
