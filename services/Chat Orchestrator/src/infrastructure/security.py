from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt

from infrastructure.config import Settings


class AuthTokenError(ValueError):
    pass


@dataclass(slots=True)
class RequestIdentity:
    user_subject: str
    user_login: str | None
    user_role: str | None
    service_id: str
    user_token: str
    service_token: str


class AuthTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._public_key = Path(settings.auth_public_key_path).read_text(encoding="utf-8")

    def _extract_bearer_token(self, header_value: str, header_name: str) -> str:
        prefix = "Bearer "
        if not header_value.startswith(prefix):
            raise AuthTokenError(f"{header_name} must use 'Bearer <token>' format")
        token = header_value[len(prefix) :].strip()
        if token == "":
            raise AuthTokenError(f"{header_name} bearer token is empty")
        return token

    def _decode_access_token(self, token: str, expected_audience: str, expected_principal_type: str) -> dict[str, Any]:
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                audience=expected_audience,
                issuer=self._settings.auth_token_issuer,
                leeway=self._settings.clock_skew_seconds,
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "iat",
                        "nbf",
                        "exp",
                        "token_kind",
                        "principal_type",
                    ]
                },
            )
        except jwt.InvalidTokenError as error:
            raise AuthTokenError("invalid JWT token") from error

        token_kind = claims.get("token_kind")
        principal_type = claims.get("principal_type")
        if token_kind != "access":
            raise AuthTokenError("token_kind must be 'access'")
        if principal_type != expected_principal_type:
            raise AuthTokenError(f"principal_type must be '{expected_principal_type}'")
        return claims

    def verify_request(
        self,
        *,
        authorization_header: str,
        service_authorization_header: str,
        service_name_header: str,
        expected_service_audience: str,
    ) -> RequestIdentity:
        user_token = self._extract_bearer_token(authorization_header, "Authorization")
        service_token = self._extract_bearer_token(service_authorization_header, "X-Service-Authorization")

        user_claims = self._decode_access_token(
            token=user_token,
            expected_audience=self._settings.user_access_token_audience,
            expected_principal_type="user",
        )
        service_claims = self._decode_access_token(
            token=service_token,
            expected_audience=expected_service_audience,
            expected_principal_type="service",
        )

        service_id = str(service_claims.get("sub", ""))
        if service_id == "":
            raise AuthTokenError("service token subject is empty")
        if service_id != service_name_header:
            raise AuthTokenError("service token subject must match X-Service-Name header")

        user_subject = str(user_claims.get("sub", ""))
        if user_subject == "":
            raise AuthTokenError("user token subject is empty")

        user_login = user_claims.get("login")
        user_role = user_claims.get("role")

        return RequestIdentity(
            user_subject=user_subject,
            user_login=str(user_login) if user_login is not None else None,
            user_role=str(user_role) if user_role is not None else None,
            service_id=service_id,
            user_token=user_token,
            service_token=service_token,
        )
