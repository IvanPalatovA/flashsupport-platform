from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import jwt

from infrastructure.config import Settings

logger = logging.getLogger(__name__)


class AuthClientError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceTokenProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._private_key = Path(settings.service_private_key_path).read_text(encoding="utf-8")
        self._cached_access_token: str | None = None
        self._cached_expires_at: datetime | None = None

    @property
    def service_id(self) -> str:
        return self._settings.service_id

    def _build_assertion(self) -> str:
        now = _utc_now()
        expires_at = now + timedelta(seconds=self._settings.service_assertion_ttl_seconds)

        payload: dict[str, Any] = {
            "iss": self._settings.service_id,
            "sub": self._settings.service_id,
            "aud": self._settings.service_assertion_audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(uuid4()),
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def _refresh_service_token(self) -> str:
        endpoint = f"{self._settings.auth_service_url.rstrip('/')}/auth/service-token"
        assertion = self._build_assertion()

        try:
            response = httpx.post(
                endpoint,
                json={
                    "service_id": self._settings.service_id,
                    "audience": self._settings.service_token_audience,
                    "assertion": assertion,
                },
                timeout=self._settings.ollama_request_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AuthClientError("failed to obtain service access token from Auth Service") from error

        try:
            payload: Any = response.json()
        except ValueError as error:
            raise AuthClientError("Auth Service returned non-JSON response") from error

        if not isinstance(payload, dict):
            raise AuthClientError("Auth Service returned invalid token payload")

        access_token = payload.get("access_token")
        access_expires_in = payload.get("access_expires_in")
        if not isinstance(access_token, str) or access_token.strip() == "":
            raise AuthClientError("Auth Service did not provide access_token")

        try:
            expires_in_seconds = int(access_expires_in)
        except (TypeError, ValueError) as error:
            raise AuthClientError("Auth Service returned invalid access_expires_in") from error

        if expires_in_seconds <= 0:
            raise AuthClientError("Auth Service returned non-positive token ttl")

        now = _utc_now()
        self._cached_access_token = access_token
        self._cached_expires_at = now + timedelta(seconds=expires_in_seconds)

        logger.info(
            "Refreshed service JWT for '%s' -> audience='%s', expires_in=%ss",
            self._settings.service_id,
            self._settings.service_token_audience,
            expires_in_seconds,
        )

        return access_token

    def get_service_access_token(self) -> str:
        now = _utc_now()
        if self._cached_access_token is not None and self._cached_expires_at is not None:
            remaining_seconds = (self._cached_expires_at - now).total_seconds()
            if remaining_seconds > self._settings.service_token_refresh_skew_seconds:
                return self._cached_access_token

        return self._refresh_service_token()
