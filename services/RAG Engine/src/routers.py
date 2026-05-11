from dataclasses import asdict
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from infrastructure.config import Settings, get_settings
from infrastructure.db import get_session
from infrastructure.embedding_runtime import EmbeddingRuntime, EmbeddingRuntimeError
from infrastructure.knowledge_repository import KnowledgeRepository
from infrastructure.llm_runtime_repository import LlmRuntimeError, LlmRuntimeRepository
from infrastructure.search_repository import SearchRepository
from infrastructure.security import AuthTokenError, AuthTokenVerifier, RequestIdentity
from models import (
    EmbeddingDownloadStatus,
    EmbeddingModelActivateRequest,
    EmbeddingModelDownloadRequest,
    EmbeddingModelsResponse,
    HealthResponse,
    KnowledgeBase,
    KnowledgeBaseCreateRequest,
    KnowledgeBasesResponse,
    KnowledgeDocument,
    KnowledgeDocumentCreateRequest,
    KnowledgeDocumentsResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from services import KnowledgeAdminService, SearchCancelledError, SearchService

router = APIRouter()


@lru_cache(maxsize=1)
def get_token_verifier() -> AuthTokenVerifier:
    return AuthTokenVerifier(get_settings())


@lru_cache(maxsize=1)
def get_embedding_runtime() -> EmbeddingRuntime:
    return EmbeddingRuntime(get_settings())


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


def get_search_service(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SearchService:
    repository = SearchRepository(session=session)
    knowledge_repository = KnowledgeRepository(session=session)
    llm_runtime = LlmRuntimeRepository(
        base_url=settings.llm_runtime_url,
        timeout_seconds=settings.llm_runtime_timeout_seconds,
    )
    return SearchService(
        repository=repository,
        settings=settings,
        llm_runtime=llm_runtime,
        knowledge_repository=knowledge_repository,
        embedding_runtime=get_embedding_runtime(),
    )


def get_knowledge_admin_service(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeAdminService:
    return KnowledgeAdminService(
        repository=KnowledgeRepository(session=session),
        settings=settings,
        embedding_runtime=get_embedding_runtime(),
    )


def _enforce_admin(identity: RequestIdentity) -> None:
    if identity.user_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role is required")


def _knowledge_base_payload(base: object) -> KnowledgeBase:
    return KnowledgeBase.model_validate(asdict(base))


def _knowledge_document_payload(document: object) -> KnowledgeDocument:
    return KnowledgeDocument.model_validate(asdict(document))


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/search", response_model=SearchResponse, tags=["search"])
def search(
    payload: SearchRequest,
    identity: RequestIdentity = Depends(require_request_identity),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    try:
        results = service.search(query=payload.query, top_k=payload.top_k)
    except SearchCancelledError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    try:
        generated = service.generate_answer(
            query=payload.query,
            contexts=results,
            user_token=identity.user_token,
            service_token=identity.service_token,
            service_name=identity.service_id,
        )
    except (RuntimeError, LlmRuntimeError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    final_top_k = payload.top_k if payload.top_k is not None else get_settings().default_top_k
    return SearchResponse(
        query=payload.query,
        top_k=final_top_k,
        results=[
            SearchResult(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                document_title=item.document_title,
                chunk_index=item.chunk_index,
                score=item.score,
                text=item.text,
            )
            for item in results
        ],
        generated_answer=generated.answer,
        llm_model=generated.model,
    )


@router.get("/embedding-models", response_model=EmbeddingModelsResponse, tags=["embedding-models"])
def list_embedding_models(
    identity: RequestIdentity = Depends(require_request_identity),
    runtime: EmbeddingRuntime = Depends(get_embedding_runtime),
) -> EmbeddingModelsResponse:
    _enforce_admin(identity)
    return EmbeddingModelsResponse.model_validate(runtime.list_models())


@router.post("/embedding-models/download", response_model=EmbeddingDownloadStatus, tags=["embedding-models"])
async def download_embedding_model(
    payload: EmbeddingModelDownloadRequest,
    identity: RequestIdentity = Depends(require_request_identity),
    runtime: EmbeddingRuntime = Depends(get_embedding_runtime),
) -> EmbeddingDownloadStatus:
    _enforce_admin(identity)
    try:
        result = await runtime.start_download(
            huggingface_url=payload.huggingface_url,
            token=payload.huggingface_token,
            model_name=payload.model_name,
            activate=payload.activate,
        )
        return EmbeddingDownloadStatus.model_validate(result)
    except EmbeddingRuntimeError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/embedding-models/download/status", response_model=EmbeddingDownloadStatus, tags=["embedding-models"])
def embedding_model_download_status(
    identity: RequestIdentity = Depends(require_request_identity),
    runtime: EmbeddingRuntime = Depends(get_embedding_runtime),
) -> EmbeddingDownloadStatus:
    _enforce_admin(identity)
    return EmbeddingDownloadStatus.model_validate(runtime.get_download_status())


@router.post("/embedding-models/activate", response_model=EmbeddingModelsResponse, tags=["embedding-models"])
def activate_embedding_model(
    payload: EmbeddingModelActivateRequest,
    identity: RequestIdentity = Depends(require_request_identity),
    runtime: EmbeddingRuntime = Depends(get_embedding_runtime),
) -> EmbeddingModelsResponse:
    _enforce_admin(identity)
    try:
        return EmbeddingModelsResponse.model_validate(runtime.activate_model(payload.model_name))
    except EmbeddingRuntimeError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/knowledge-bases", response_model=KnowledgeBasesResponse, tags=["knowledge-bases"])
def list_knowledge_bases(
    identity: RequestIdentity = Depends(require_request_identity),
    service: KnowledgeAdminService = Depends(get_knowledge_admin_service),
) -> KnowledgeBasesResponse:
    _enforce_admin(identity)
    return KnowledgeBasesResponse(bases=[_knowledge_base_payload(item) for item in service.list_bases()])


@router.post("/knowledge-bases", response_model=KnowledgeBase, status_code=status.HTTP_201_CREATED, tags=["knowledge-bases"])
def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    identity: RequestIdentity = Depends(require_request_identity),
    service: KnowledgeAdminService = Depends(get_knowledge_admin_service),
) -> KnowledgeBase:
    _enforce_admin(identity)
    try:
        result = service.create_base(
            name=payload.name,
            description=payload.description,
            documents=[item.model_dump() for item in payload.documents],
            metadata=payload.metadata,
            activate=payload.activate,
        )
        return _knowledge_base_payload(result)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/knowledge-bases/{knowledge_base_id}/activate", response_model=KnowledgeBase, tags=["knowledge-bases"])
def activate_knowledge_base(
    knowledge_base_id: int,
    identity: RequestIdentity = Depends(require_request_identity),
    service: KnowledgeAdminService = Depends(get_knowledge_admin_service),
) -> KnowledgeBase:
    _enforce_admin(identity)
    try:
        return _knowledge_base_payload(service.activate_base(knowledge_base_id))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.delete("/knowledge-bases/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["knowledge-bases"])
def delete_knowledge_base(
    knowledge_base_id: int,
    identity: RequestIdentity = Depends(require_request_identity),
    service: KnowledgeAdminService = Depends(get_knowledge_admin_service),
) -> None:
    _enforce_admin(identity)
    try:
        service.delete_base(knowledge_base_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/knowledge-bases/{knowledge_base_id}/documents", response_model=KnowledgeDocumentsResponse, tags=["knowledge-bases"])
def list_knowledge_documents(
    knowledge_base_id: int,
    identity: RequestIdentity = Depends(require_request_identity),
    service: KnowledgeAdminService = Depends(get_knowledge_admin_service),
) -> KnowledgeDocumentsResponse:
    _enforce_admin(identity)
    return KnowledgeDocumentsResponse(
        documents=[_knowledge_document_payload(item) for item in service.list_documents(knowledge_base_id)]
    )


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=KnowledgeDocument,
    status_code=status.HTTP_201_CREATED,
    tags=["knowledge-bases"],
)
def add_knowledge_document(
    knowledge_base_id: int,
    payload: KnowledgeDocumentCreateRequest,
    identity: RequestIdentity = Depends(require_request_identity),
    service: KnowledgeAdminService = Depends(get_knowledge_admin_service),
) -> KnowledgeDocument:
    _enforce_admin(identity)
    try:
        return _knowledge_document_payload(
            service.add_document(
                knowledge_base_id=knowledge_base_id,
                title=payload.title,
                text=payload.text,
                source=payload.source,
                metadata=payload.metadata,
            )
        )
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.delete(
    "/knowledge-bases/{knowledge_base_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["knowledge-bases"],
)
def delete_knowledge_document(
    knowledge_base_id: int,
    document_id: int,
    identity: RequestIdentity = Depends(require_request_identity),
    service: KnowledgeAdminService = Depends(get_knowledge_admin_service),
) -> None:
    _enforce_admin(identity)
    try:
        service.delete_document(knowledge_base_id=knowledge_base_id, document_id=document_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
