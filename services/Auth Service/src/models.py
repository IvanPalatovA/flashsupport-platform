from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class RegisterUserRequest(BaseModel):
    login: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="registered_user", min_length=2, max_length=32)


class RegisterUserResponse(BaseModel):
    user_id: str
    login: str
    role: str


class UserLoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class TokenPairResponse(BaseModel):
    token_type: str = "Bearer"
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int


class ServiceTokenRequest(BaseModel):
    service_id: str = Field(min_length=2, max_length=128)
    audience: str = Field(min_length=2, max_length=128)
    assertion: str = Field(min_length=32)


class ServiceTokenResponse(BaseModel):
    token_type: str = "Bearer"
    access_token: str
    access_expires_in: int
