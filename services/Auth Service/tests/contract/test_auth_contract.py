import os

from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_SERVICE_ENV", "dev")
os.environ.setdefault("SKIP_SCHEMA_INIT", "true")

from domain import ServiceTokenEntity, TokenPairEntity, UserEntity
from main import app
from models import RegisterUserResponse, ServiceTokenResponse, TokenPairResponse
from routers import get_auth_service


class FakeAuthService:
    def register_user(self, login: str, password: str, role: str) -> UserEntity:
        _ = password
        return UserEntity(user_id="user-1", login=login, role=role, is_active=True)

    def login_user(self, login: str, password: str) -> TokenPairEntity:
        _ = login
        _ = password
        return TokenPairEntity(
            access_token="access-token",
            refresh_token="refresh-token",
            access_expires_in=900,
            refresh_expires_in=1296000,
            refresh_jti="jti-1",
        )

    def refresh_user_tokens(self, refresh_token: str) -> TokenPairEntity:
        _ = refresh_token
        return TokenPairEntity(
            access_token="access-token-2",
            refresh_token="refresh-token-2",
            access_expires_in=900,
            refresh_expires_in=1296000,
            refresh_jti="jti-2",
        )

    def issue_service_token(self, service_id: str, audience: str, assertion: str) -> ServiceTokenEntity:
        _ = service_id
        _ = audience
        _ = assertion
        return ServiceTokenEntity(access_token="service-access", expires_in=900)


def test_auth_contract_models() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    client = TestClient(app)

    register_response = client.post(
        "/auth/register",
        json={"login": "alice", "password": "password123", "role": "registered_user"},
    )
    login_response = client.post(
        "/auth/login",
        json={"login": "alice", "password": "password123"},
    )
    service_token_response = client.post(
        "/auth/service-token",
        json={
            "service_id": "chat-orchestrator",
            "audience": "rag-service",
            "assertion": "assertion-token-abcdefghijklmnopqrstuvwxyz",
        },
    )

    assert register_response.status_code == 201
    assert login_response.status_code == 200
    assert service_token_response.status_code == 200

    RegisterUserResponse.model_validate(register_response.json())
    TokenPairResponse.model_validate(login_response.json())
    ServiceTokenResponse.model_validate(service_token_response.json())

    app.dependency_overrides.clear()
