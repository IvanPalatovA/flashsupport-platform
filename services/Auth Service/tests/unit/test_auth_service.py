from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from domain import ServiceAssertionEntity, ServiceTokenEntity, TokenPairEntity, UserAuthEntity, UserEntity
from infrastructure.config import Settings
from infrastructure.repositories import UserLoginAlreadyExistsError
from services import AuthService, InvalidRefreshTokenError, ServiceAssertionRejectedError


class FakeRepository:
    def __init__(self) -> None:
        self.users: dict[str, UserAuthEntity] = {}
        self.refresh_tokens: dict[str, tuple[str, datetime, datetime | None]] = {}
        self.service_keys: dict[str, str] = {"chat-orchestrator": "PUB"}
        self.used_assertions: set[str] = set()
        self._commits = 0

    def commit(self) -> None:
        self._commits += 1

    def rollback(self) -> None:
        pass

    def create_user(self, login: str, password_hash: str, role: str, encryption_key: str) -> UserEntity:
        _ = encryption_key
        if login in self.users:
            raise UserLoginAlreadyExistsError("duplicate")
        user = UserAuthEntity(
            user_id=f"user-{len(self.users) + 1}",
            login=login,
            role=role,
            is_active=True,
            password_hash=password_hash,
        )
        self.users[login] = user
        return UserEntity(user_id=user.user_id, login=user.login, role=user.role, is_active=True)

    def get_user_auth_by_login(self, login: str, encryption_key: str) -> UserAuthEntity | None:
        _ = encryption_key
        return self.users.get(login)

    def store_refresh_token(self, jti: str, user_id: str, expires_at: datetime) -> None:
        self.refresh_tokens[jti] = (user_id, expires_at, None)

    def get_refresh_token(self, jti: str):  # noqa: ANN001
        if jti not in self.refresh_tokens:
            return None
        user_id, expires_at, revoked_at = self.refresh_tokens[jti]

        class RefreshRecord:
            def __init__(self, token_jti: str, uid: str, exp: datetime, rev: datetime | None) -> None:
                self.jti = token_jti
                self.user_id = uid
                self.expires_at = exp
                self.revoked_at = rev

        return RefreshRecord(jti, user_id, expires_at, revoked_at)

    def revoke_refresh_token(self, jti: str) -> bool:
        if jti not in self.refresh_tokens:
            return False
        user_id, expires_at, revoked_at = self.refresh_tokens[jti]
        if revoked_at is not None:
            return False
        self.refresh_tokens[jti] = (user_id, expires_at, datetime.now(timezone.utc))
        return True

    def get_service_public_key(self, service_id: str) -> str | None:
        return self.service_keys.get(service_id)

    def register_assertion_jti(self, jti: str, service_id: str, expires_at: datetime) -> bool:
        _ = service_id
        _ = expires_at
        if jti in self.used_assertions:
            return False
        self.used_assertions.add(jti)
        return True

    def purge_expired(self, now: datetime | None = None) -> None:
        _ = now

    def load_service_public_keys_from_dir(self, directory: str) -> int:
        _ = directory
        return 1


class FakeTokenManager:
    def hash_password(self, password: str) -> str:
        return f"hash::{password}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hash::{password}"

    def issue_user_token_pair(self, user_id: str, login: str, role: str) -> TokenPairEntity:
        jti = str(uuid4())
        return TokenPairEntity(
            access_token=f"access::{user_id}",
            refresh_token=f"refresh::{jti}::{user_id}::{login}::{role}",
            access_expires_in=900,
            refresh_expires_in=15 * 24 * 60 * 60,
            refresh_jti=jti,
        )

    def decode_refresh_token(self, refresh_token: str):  # noqa: ANN001
        parts = refresh_token.split("::")
        if len(parts) != 5:
            raise ValueError("bad token")
        _, jti, user_id, login, role = parts
        return {
            "jti": jti,
            "sub": user_id,
            "login": login,
            "role": role,
        }

    def verify_service_assertion(self, assertion: str, service_id: str, service_public_key: str) -> ServiceAssertionEntity:
        _ = service_public_key
        return ServiceAssertionEntity(
            jti=assertion,
            service_id=service_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )

    def issue_service_access_token(self, service_id: str, audience: str) -> ServiceTokenEntity:
        return ServiceTokenEntity(access_token=f"service::{service_id}::{audience}", expires_in=900)


def build_service() -> tuple[AuthService, FakeRepository]:
    repository = FakeRepository()
    settings = Settings(
        app_name="auth-service",
        env="test",
        host="0.0.0.0",
        port=8070,
        log_level="INFO",
        database_url="postgresql+psycopg://user:pass@localhost:5432/db",
        database_encryption_key="test_key_01234567890123456789",
        token_issuer="flashsupport-auth-service",
        user_access_token_audience="flashsupport-services",
        service_assertion_audience="auth-service",
        auth_private_key_path="private.pem",
        auth_public_key_path="public.pem",
        service_public_keys_dir="keys",
        user_access_token_ttl_minutes=15,
        user_refresh_token_ttl_days=15,
        service_access_token_ttl_minutes=15,
        bcrypt_rounds=12,
        clock_skew_seconds=10,
        skip_schema_init=True,
    )
    service = AuthService(repository=repository, token_manager=FakeTokenManager(), settings=settings)
    return service, repository


def test_register_and_login_happy_path() -> None:
    service, repository = build_service()

    user = service.register_user(login="alice", password="password123", role="registered_user")
    tokens = service.login_user(login="alice", password="password123")

    assert user.login == "alice"
    assert tokens.access_expires_in == 900
    assert tokens.refresh_jti in repository.refresh_tokens


def test_refresh_rotates_token() -> None:
    service, repository = build_service()
    service.register_user(login="bob", password="password123", role="registered_user")
    first_tokens = service.login_user(login="bob", password="password123")

    second_tokens = service.refresh_user_tokens(refresh_token=first_tokens.refresh_token)

    assert second_tokens.refresh_jti != first_tokens.refresh_jti
    old_record = repository.refresh_tokens[first_tokens.refresh_jti]
    assert old_record[2] is not None


def test_refresh_rejects_unknown_token() -> None:
    service, _ = build_service()

    try:
        service.refresh_user_tokens("refresh::missing::user::login::role")
        assert False, "Expected InvalidRefreshTokenError"
    except InvalidRefreshTokenError:
        assert True


def test_service_assertion_replay_is_rejected() -> None:
    service, _ = build_service()

    first = service.issue_service_token(
        service_id="chat-orchestrator",
        audience="rag-service",
        assertion="assertion-1",
    )
    assert first.expires_in == 900

    try:
        service.issue_service_token(
            service_id="chat-orchestrator",
            audience="rag-service",
            assertion="assertion-1",
        )
        assert False, "Expected ServiceAssertionRejectedError"
    except ServiceAssertionRejectedError:
        assert True
