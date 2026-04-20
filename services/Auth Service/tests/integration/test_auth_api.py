import os

from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_SERVICE_ENV", "dev")
os.environ.setdefault("SKIP_SCHEMA_INIT", "true")

from domain import ServiceTokenEntity, TokenPairEntity, UserEntity
from main import app
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


def test_register_endpoint_happy_path() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    client = TestClient(app)

    response = client.post(
        "/auth/register",
        json={"login": "alice", "password": "password123", "role": "registered_user"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["login"] == "alice"
    assert payload["role"] == "registered_user"

    app.dependency_overrides.clear()


def test_login_endpoint_happy_path() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={"login": "alice", "password": "password123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "access-token"
    assert payload["refresh_token"] == "refresh-token"

    app.dependency_overrides.clear()


def test_login_endpoint_validation_error() -> None:
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={"login": "a", "password": "short"},
    )

    assert response.status_code == 422
