from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from infrastructure.config import Settings, get_settings
from infrastructure.db import get_session
from infrastructure.repositories import AuthRepository
from infrastructure.security import TokenManager
from models import (
    HealthResponse,
    RefreshTokenRequest,
    RegisterUserRequest,
    RegisterUserResponse,
    ServiceTokenRequest,
    ServiceTokenResponse,
    TokenPairResponse,
    UserLoginRequest,
)
from services import (
    AuthService,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidRoleError,
    LoginAlreadyExistsError,
    ServiceAssertionRejectedError,
)

router = APIRouter()


@lru_cache(maxsize=1)
def get_token_manager() -> TokenManager:
    return TokenManager(get_settings())


def get_auth_service(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    repository = AuthRepository(session=session)
    return AuthService(repository=repository, token_manager=get_token_manager(), settings=settings)


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/auth/register", response_model=RegisterUserResponse, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register_user(
    payload: RegisterUserRequest,
    service: AuthService = Depends(get_auth_service),
) -> RegisterUserResponse:
    try:
        user = service.register_user(login=payload.login, password=payload.password, role=payload.role)
    except LoginAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except InvalidRoleError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return RegisterUserResponse(user_id=user.user_id, login=user.login, role=user.role)


@router.post("/auth/login", response_model=TokenPairResponse, tags=["auth"])
def login_user(
    payload: UserLoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenPairResponse:
    try:
        token_pair = service.login_user(login=payload.login, password=payload.password)
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

    return TokenPairResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        access_expires_in=token_pair.access_expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


@router.post("/auth/refresh", response_model=TokenPairResponse, tags=["auth"])
def refresh_user_tokens(
    payload: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenPairResponse:
    try:
        token_pair = service.refresh_user_tokens(refresh_token=payload.refresh_token)
    except InvalidRefreshTokenError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

    return TokenPairResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        access_expires_in=token_pair.access_expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


@router.post("/auth/service-token", response_model=ServiceTokenResponse, tags=["auth"])
def issue_service_token(
    payload: ServiceTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> ServiceTokenResponse:
    try:
        token = service.issue_service_token(
            service_id=payload.service_id,
            audience=payload.audience,
            assertion=payload.assertion,
        )
    except ServiceAssertionRejectedError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

    return ServiceTokenResponse(access_token=token.access_token, access_expires_in=token.expires_in)
