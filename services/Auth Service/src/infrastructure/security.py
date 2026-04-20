from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import bcrypt
import jwt

from domain import ServiceAssertionEntity, ServiceTokenEntity, TokenPairEntity
from infrastructure.config import Settings


class SecurityError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_timestamp(value: datetime) -> int:
    return int(value.timestamp())


class TokenManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._private_key = Path(settings.auth_private_key_path).read_text(encoding="utf-8")
        self._public_key = Path(settings.auth_public_key_path).read_text(encoding="utf-8")

    def hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self._settings.bcrypt_rounds)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify_password(self, password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    def issue_user_token_pair(self, user_id: str, login: str, role: str) -> TokenPairEntity:
        now = _utc_now()
        access_expires_at = now + timedelta(minutes=self._settings.user_access_token_ttl_minutes)
        refresh_expires_at = now + timedelta(days=self._settings.user_refresh_token_ttl_days)
        refresh_jti = str(uuid4())

        access_payload: dict[str, Any] = {
            "iss": self._settings.token_issuer,
            "sub": user_id,
            "aud": self._settings.user_access_token_audience,
            "iat": _as_timestamp(now),
            "nbf": _as_timestamp(now),
            "exp": _as_timestamp(access_expires_at),
            "token_kind": "access",
            "principal_type": "user",
            "login": login,
            "role": role,
        }
        refresh_payload: dict[str, Any] = {
            "iss": self._settings.token_issuer,
            "sub": user_id,
            "aud": self._settings.token_issuer,
            "iat": _as_timestamp(now),
            "nbf": _as_timestamp(now),
            "exp": _as_timestamp(refresh_expires_at),
            "jti": refresh_jti,
            "token_kind": "refresh",
            "principal_type": "user",
            "login": login,
            "role": role,
        }

        access_token = jwt.encode(access_payload, self._private_key, algorithm="RS256")
        refresh_token = jwt.encode(refresh_payload, self._private_key, algorithm="RS256")

        return TokenPairEntity(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=int((access_expires_at - now).total_seconds()),
            refresh_expires_in=int((refresh_expires_at - now).total_seconds()),
            refresh_jti=refresh_jti,
        )

    def decode_refresh_token(self, refresh_token: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                refresh_token,
                self._public_key,
                algorithms=["RS256"],
                audience=self._settings.token_issuer,
                issuer=self._settings.token_issuer,
                leeway=self._settings.clock_skew_seconds,
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "iat",
                        "nbf",
                        "exp",
                        "jti",
                        "token_kind",
                        "principal_type",
                    ]
                },
            )
        except jwt.InvalidTokenError as error:
            raise SecurityError("invalid refresh token") from error

        if payload.get("token_kind") != "refresh":
            raise SecurityError("provided token is not a refresh token")
        if payload.get("principal_type") != "user":
            raise SecurityError("refresh token principal_type must be 'user'")

        return payload

    def verify_service_assertion(self, assertion: str, service_id: str, service_public_key: str) -> ServiceAssertionEntity:
        try:
            payload = jwt.decode(
                assertion,
                service_public_key,
                algorithms=["RS256"],
                audience=self._settings.service_assertion_audience,
                issuer=service_id,
                leeway=self._settings.clock_skew_seconds,
                options={
                    "require": ["iss", "sub", "aud", "iat", "nbf", "exp", "jti"],
                },
            )
        except jwt.InvalidTokenError as error:
            raise SecurityError("invalid service assertion") from error

        if str(payload.get("sub")) != service_id:
            raise SecurityError("service assertion subject does not match service_id")

        jti = str(payload.get("jti"))
        if not jti:
            raise SecurityError("service assertion jti is empty")

        exp_value = payload.get("exp")
        if not isinstance(exp_value, int):
            raise SecurityError("service assertion exp must be integer timestamp")

        expires_at = datetime.fromtimestamp(exp_value, tz=timezone.utc)
        return ServiceAssertionEntity(jti=jti, service_id=service_id, expires_at=expires_at)

    def issue_service_access_token(self, service_id: str, audience: str) -> ServiceTokenEntity:
        now = _utc_now()
        expires_at = now + timedelta(minutes=self._settings.service_access_token_ttl_minutes)

        payload: dict[str, Any] = {
            "iss": self._settings.token_issuer,
            "sub": service_id,
            "aud": audience,
            "iat": _as_timestamp(now),
            "nbf": _as_timestamp(now),
            "exp": _as_timestamp(expires_at),
            "token_kind": "access",
            "principal_type": "service",
        }
        access_token = jwt.encode(payload, self._private_key, algorithm="RS256")

        return ServiceTokenEntity(
            access_token=access_token,
            expires_in=int((expires_at - now).total_seconds()),
        )
