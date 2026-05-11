from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from infrastructure.config import Settings, get_settings
from infrastructure.db import get_session
from infrastructure.llm_runtime_repository import LlmRuntimeError, LlmRuntimeRepository
from infrastructure.search_repository import SearchRepository
from infrastructure.security import AuthTokenError, AuthTokenVerifier, RequestIdentity
from models import HealthResponse, SearchRequest, SearchResponse, SearchResult
from services import SearchService

router = APIRouter()


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


def get_search_service(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SearchService:
    repository = SearchRepository(session=session)
    llm_runtime = LlmRuntimeRepository(
        base_url=settings.llm_runtime_url,
        timeout_seconds=settings.llm_runtime_timeout_seconds,
    )
    return SearchService(repository=repository, settings=settings, llm_runtime=llm_runtime)


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/search", response_model=SearchResponse, tags=["search"])
def search(
    payload: SearchRequest,
    identity: RequestIdentity = Depends(require_request_identity),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    results = service.search(query=payload.query, top_k=payload.top_k)
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
