from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str
    env: str
    host: str
    port: int
    log_level: str
    database_url: str
    database_encryption_key: str = Field(min_length=16)
    token_issuer: str
    user_access_token_audience: str
    service_assertion_audience: str
    auth_private_key_path: str
    auth_public_key_path: str
    service_public_keys_dir: str
    user_access_token_ttl_minutes: int = Field(gt=0, le=120)
    user_refresh_token_ttl_days: int = Field(gt=0, le=365)
    service_access_token_ttl_minutes: int = Field(gt=0, le=120)
    bcrypt_rounds: int = Field(ge=10, le=15)
    clock_skew_seconds: int = Field(ge=0, le=300)
    skip_schema_init: bool = False


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        loaded: Any = yaml.safe_load(file) or {}
        if not isinstance(loaded, dict):
            return {}
        return cast(dict[str, Any], loaded)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(override)
    return merged


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _get_from_env_or_yaml(env_name: str, env_value: str | None, data: dict[str, Any], key: str) -> Any:
    if env_value is not None and env_value != "":
        return env_value

    if key in data and data[key] not in (None, ""):
        return data[key]

    raise ValueError(
        f"Missing required setting '{key}' for AUTH_SERVICE_ENV='{env_name}'. "
        f"Set env var or define it in config/{env_name}.yaml or config/base.yaml"
    )


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Cannot parse boolean from value: {value}")


def _resolve_path(service_root: Path, raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return str(path)
    return str((service_root / path).resolve())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    service_root = Path(__file__).resolve().parents[2]
    config_dir = service_root / "config"

    env_name = _required_env("AUTH_SERVICE_ENV")
    env_config_path = config_dir / f"{env_name}.yaml"
    if not env_config_path.exists():
        raise FileNotFoundError(f"Environment config file not found: {env_config_path}")

    data = _merge(_read_yaml(config_dir / "base.yaml"), _read_yaml(env_config_path))

    private_key_path = _resolve_path(
        service_root,
        str(_get_from_env_or_yaml(env_name, os.getenv("AUTH_PRIVATE_KEY_PATH"), data, "auth_private_key_path")),
    )
    public_key_path = _resolve_path(
        service_root,
        str(_get_from_env_or_yaml(env_name, os.getenv("AUTH_PUBLIC_KEY_PATH"), data, "auth_public_key_path")),
    )
    service_public_keys_dir = _resolve_path(
        service_root,
        str(_get_from_env_or_yaml(env_name, os.getenv("SERVICE_PUBLIC_KEYS_DIR"), data, "service_public_keys_dir")),
    )

    env_overrides: dict[str, Any] = {
        "env": env_name,
        "app_name": _get_from_env_or_yaml(env_name, os.getenv("APP_NAME"), data, "app_name"),
        "host": _get_from_env_or_yaml(env_name, os.getenv("APP_HOST"), data, "host"),
        "port": int(_get_from_env_or_yaml(env_name, os.getenv("APP_PORT"), data, "port")),
        "log_level": _get_from_env_or_yaml(env_name, os.getenv("LOG_LEVEL"), data, "log_level"),
        "database_url": _get_from_env_or_yaml(env_name, os.getenv("DATABASE_URL"), data, "database_url"),
        "database_encryption_key": _get_from_env_or_yaml(
            env_name,
            os.getenv("DATABASE_ENCRYPTION_KEY"),
            data,
            "database_encryption_key",
        ),
        "token_issuer": _get_from_env_or_yaml(env_name, os.getenv("TOKEN_ISSUER"), data, "token_issuer"),
        "user_access_token_audience": _get_from_env_or_yaml(
            env_name,
            os.getenv("USER_ACCESS_TOKEN_AUDIENCE"),
            data,
            "user_access_token_audience",
        ),
        "service_assertion_audience": _get_from_env_or_yaml(
            env_name,
            os.getenv("SERVICE_ASSERTION_AUDIENCE"),
            data,
            "service_assertion_audience",
        ),
        "auth_private_key_path": private_key_path,
        "auth_public_key_path": public_key_path,
        "service_public_keys_dir": service_public_keys_dir,
        "user_access_token_ttl_minutes": int(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("USER_ACCESS_TOKEN_TTL_MINUTES"),
                data,
                "user_access_token_ttl_minutes",
            )
        ),
        "user_refresh_token_ttl_days": int(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("USER_REFRESH_TOKEN_TTL_DAYS"),
                data,
                "user_refresh_token_ttl_days",
            )
        ),
        "service_access_token_ttl_minutes": int(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("SERVICE_ACCESS_TOKEN_TTL_MINUTES"),
                data,
                "service_access_token_ttl_minutes",
            )
        ),
        "bcrypt_rounds": int(_get_from_env_or_yaml(env_name, os.getenv("BCRYPT_ROUNDS"), data, "bcrypt_rounds")),
        "clock_skew_seconds": int(
            _get_from_env_or_yaml(env_name, os.getenv("CLOCK_SKEW_SECONDS"), data, "clock_skew_seconds")
        ),
        "skip_schema_init": _as_bool(
            _get_from_env_or_yaml(env_name, os.getenv("SKIP_SCHEMA_INIT"), data, "skip_schema_init")
        ),
    }

    return Settings(**_merge(data, env_overrides))
