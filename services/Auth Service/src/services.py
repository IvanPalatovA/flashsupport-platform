from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain import ServiceTokenEntity, TokenPairEntity, UserEntity
from infrastructure.config import Settings
from infrastructure.repositories import AuthRepository, UserLoginAlreadyExistsError
from infrastructure.security import SecurityError, TokenManager

_ALLOWED_REGISTRATION_ROLES = {"registered_user", "operator", "specialist", "admin"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthServiceError(RuntimeError):
    pass


class InvalidCredentialsError(AuthServiceError):
    pass


class InvalidRefreshTokenError(AuthServiceError):
    pass


class LoginAlreadyExistsError(AuthServiceError):
    pass


class InvalidRoleError(AuthServiceError):
    pass


class ServiceAssertionRejectedError(AuthServiceError):
    pass


class AuthService:
    def __init__(self, repository: AuthRepository, token_manager: TokenManager, settings: Settings) -> None:
        self._repository = repository
        self._token_manager = token_manager
        self._settings = settings

    def register_user(self, login: str, password: str, role: str) -> UserEntity:
        normalized_role = role.strip().lower()
        if normalized_role not in _ALLOWED_REGISTRATION_ROLES:
            allowed = ", ".join(sorted(_ALLOWED_REGISTRATION_ROLES))
            raise InvalidRoleError(f"role must be one of: {allowed}")

        password_hash = self._token_manager.hash_password(password)
        try:
            user = self._repository.create_user(
                login=login,
                password_hash=password_hash,
                role=normalized_role,
                encryption_key=self._settings.database_encryption_key,
            )
            self._repository.commit()
        except UserLoginAlreadyExistsError as error:
            self._repository.rollback()
            raise LoginAlreadyExistsError(str(error)) from error
        except Exception:
            self._repository.rollback()
            raise

        return user

    def login_user(self, login: str, password: str) -> TokenPairEntity:
        user = self._repository.get_user_auth_by_login(
            login=login,
            encryption_key=self._settings.database_encryption_key,
        )
        if user is None or not user.is_active:
            raise InvalidCredentialsError("invalid login or password")

        if not self._token_manager.verify_password(password=password, password_hash=user.password_hash):
            raise InvalidCredentialsError("invalid login or password")

        token_pair = self._token_manager.issue_user_token_pair(
            user_id=user.user_id,
            login=user.login,
            role=user.role,
        )

        refresh_expires_at = _utc_now() + timedelta(seconds=token_pair.refresh_expires_in)
        try:
            self._repository.store_refresh_token(
                jti=token_pair.refresh_jti,
                user_id=user.user_id,
                expires_at=refresh_expires_at,
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise

        return token_pair

    def refresh_user_tokens(self, refresh_token: str) -> TokenPairEntity:
        try:
            payload = self._token_manager.decode_refresh_token(refresh_token)
        except SecurityError as error:
            raise InvalidRefreshTokenError(str(error)) from error

        jti = str(payload.get("jti"))
        user_id = str(payload.get("sub"))
        login = str(payload.get("login"))
        role = str(payload.get("role"))

        if not jti or not user_id:
            raise InvalidRefreshTokenError("refresh token payload is incomplete")

        token_record = self._repository.get_refresh_token(jti=jti)
        now = _utc_now()
        if token_record is None:
            raise InvalidRefreshTokenError("refresh token is not recognized")
        if token_record.revoked_at is not None:
            raise InvalidRefreshTokenError("refresh token has been revoked")
        if token_record.expires_at <= now:
            raise InvalidRefreshTokenError("refresh token has expired")

        new_pair = self._token_manager.issue_user_token_pair(user_id=user_id, login=login, role=role)
        new_expires_at = now + timedelta(seconds=new_pair.refresh_expires_in)

        try:
            revoked = self._repository.revoke_refresh_token(jti=jti)
            if not revoked:
                self._repository.rollback()
                raise InvalidRefreshTokenError("refresh token is already rotated")

            self._repository.store_refresh_token(
                jti=new_pair.refresh_jti,
                user_id=user_id,
                expires_at=new_expires_at,
            )
            self._repository.purge_expired(now=now)
            self._repository.commit()
        except InvalidRefreshTokenError:
            raise
        except Exception:
            self._repository.rollback()
            raise

        return new_pair

    def issue_service_token(self, service_id: str, audience: str, assertion: str) -> ServiceTokenEntity:
        public_key = self._repository.get_service_public_key(service_id=service_id)
        if public_key is None:
            raise ServiceAssertionRejectedError(f"unknown service_id '{service_id}'")

        try:
            assertion_data = self._token_manager.verify_service_assertion(
                assertion=assertion,
                service_id=service_id,
                service_public_key=public_key,
            )
        except SecurityError as error:
            raise ServiceAssertionRejectedError(str(error)) from error

        try:
            accepted = self._repository.register_assertion_jti(
                jti=assertion_data.jti,
                service_id=assertion_data.service_id,
                expires_at=assertion_data.expires_at,
            )
            if not accepted:
                self._repository.rollback()
                raise ServiceAssertionRejectedError("service assertion replay detected")

            token = self._token_manager.issue_service_access_token(service_id=service_id, audience=audience)
            self._repository.purge_expired(now=_utc_now())
            self._repository.commit()
        except ServiceAssertionRejectedError:
            raise
        except Exception:
            self._repository.rollback()
            raise

        return token

    def sync_service_public_keys(self) -> int:
        try:
            count = self._repository.load_service_public_keys_from_dir(self._settings.service_public_keys_dir)
            self._repository.commit()
            return count
        except Exception:
            self._repository.rollback()
            raise
