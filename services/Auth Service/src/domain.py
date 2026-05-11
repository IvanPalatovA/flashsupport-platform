from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class UserEntity:
    user_id: str
    login: str
    role: str
    is_active: bool


@dataclass(slots=True)
class UserAuthEntity:
    user_id: str
    login: str
    role: str
    is_active: bool
    password_hash: str


@dataclass(slots=True)
class RefreshTokenRecordEntity:
    jti: str
    user_id: str
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(slots=True)
class TokenPairEntity:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int
    refresh_jti: str


@dataclass(slots=True)
class ServiceTokenEntity:
    access_token: str
    expires_in: int


@dataclass(slots=True)
class ServiceAssertionEntity:
    jti: str
    service_id: str
    expires_at: datetime
