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
    ollama_base_url: str
    llm_model_name: str
    llm_system_prompt: str
    llm_temperature: float = Field(ge=0.0, le=2.0)
    llm_top_p: float = Field(gt=0.0, le=1.0)
    llm_max_tokens: int = Field(ge=1, le=16384)
    ollama_request_timeout_seconds: float = Field(gt=0.0, le=600.0)
    max_concurrent_inferences: int = Field(ge=1, le=32)
    inference_queue_capacity: int = Field(ge=1, le=10000)
    inference_wait_timeout_seconds: float = Field(gt=0.0, le=3600.0)
    enforce_service_identity: bool = True
    auth_service_url: str
    auth_public_key_path: str
    auth_token_issuer: str
    user_access_token_audience: str
    incoming_service_token_audience: str
    allowed_caller_service_ids: list[str]
    service_id: str
    service_private_key_path: str
    service_token_audience: str
    service_assertion_audience: str
    service_assertion_ttl_seconds: int = Field(gt=0, le=300)
    service_token_refresh_skew_seconds: int = Field(ge=0, le=600)
    clock_skew_seconds: int = Field(ge=0, le=300)


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


def _resolve_path(service_root: Path, raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return str(path)
    return str((service_root / path).resolve())


def _get_from_env_or_yaml(env_name: str, env_value: str | None, data: dict[str, Any], key: str) -> Any:
    if env_value is not None and env_value != "":
        return env_value

    if key in data and data[key] not in (None, ""):
        return data[key]

    raise ValueError(
        f"Missing required setting '{key}' for LLM_RUNTIME_ENV='{env_name}'. "
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


def _as_non_empty_str_list(value: Any) -> list[str]:
    raw_items: list[Any]
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    else:
        raise ValueError(f"Cannot parse list from value: {value}")

    items = [str(item).strip() for item in raw_items if str(item).strip() != ""]
    if not items:
        raise ValueError("allowed_caller_service_ids must contain at least one service id")
    return items


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    service_root = Path(__file__).resolve().parents[2]
    config_dir = service_root / "config"

    env_name = _required_env("LLM_RUNTIME_ENV")
    env_config_path = config_dir / f"{env_name}.yaml"
    if not env_config_path.exists():
        raise FileNotFoundError(f"Environment config file not found: {env_config_path}")

    data = _merge(_read_yaml(config_dir / "base.yaml"), _read_yaml(env_config_path))

    auth_public_key_path = _resolve_path(
        service_root,
        str(_get_from_env_or_yaml(env_name, os.getenv("AUTH_PUBLIC_KEY_PATH"), data, "auth_public_key_path")),
    )
    service_private_key_path = _resolve_path(
        service_root,
        str(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("SERVICE_PRIVATE_KEY_PATH"),
                data,
                "service_private_key_path",
            )
        ),
    )

    env_overrides: dict[str, Any] = {
        "env": env_name,
        "app_name": _get_from_env_or_yaml(env_name, os.getenv("APP_NAME"), data, "app_name"),
        "host": _get_from_env_or_yaml(env_name, os.getenv("APP_HOST"), data, "host"),
        "port": int(_get_from_env_or_yaml(env_name, os.getenv("APP_PORT"), data, "port")),
        "log_level": _get_from_env_or_yaml(env_name, os.getenv("LOG_LEVEL"), data, "log_level"),
        "ollama_base_url": _get_from_env_or_yaml(env_name, os.getenv("OLLAMA_BASE_URL"), data, "ollama_base_url"),
        "llm_model_name": _get_from_env_or_yaml(env_name, os.getenv("LLM_MODEL_NAME"), data, "llm_model_name"),
        "llm_system_prompt": _get_from_env_or_yaml(
            env_name,
            os.getenv("LLM_SYSTEM_PROMPT"),
            data,
            "llm_system_prompt",
        ),
        "llm_temperature": float(
            _get_from_env_or_yaml(env_name, os.getenv("LLM_TEMPERATURE"), data, "llm_temperature")
        ),
        "llm_top_p": float(_get_from_env_or_yaml(env_name, os.getenv("LLM_TOP_P"), data, "llm_top_p")),
        "llm_max_tokens": int(_get_from_env_or_yaml(env_name, os.getenv("LLM_MAX_TOKENS"), data, "llm_max_tokens")),
        "ollama_request_timeout_seconds": float(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS"),
                data,
                "ollama_request_timeout_seconds",
            )
        ),
        "max_concurrent_inferences": int(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("MAX_CONCURRENT_INFERENCES"),
                data,
                "max_concurrent_inferences",
            )
        ),
        "inference_queue_capacity": int(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("INFERENCE_QUEUE_CAPACITY"),
                data,
                "inference_queue_capacity",
            )
        ),
        "inference_wait_timeout_seconds": float(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("INFERENCE_WAIT_TIMEOUT_SECONDS"),
                data,
                "inference_wait_timeout_seconds",
            )
        ),
        "enforce_service_identity": _as_bool(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("ENFORCE_SERVICE_IDENTITY"),
                data,
                "enforce_service_identity",
            )
        ),
        "auth_service_url": _get_from_env_or_yaml(env_name, os.getenv("AUTH_SERVICE_URL"), data, "auth_service_url"),
        "auth_public_key_path": auth_public_key_path,
        "auth_token_issuer": _get_from_env_or_yaml(
            env_name,
            os.getenv("AUTH_TOKEN_ISSUER"),
            data,
            "auth_token_issuer",
        ),
        "user_access_token_audience": _get_from_env_or_yaml(
            env_name,
            os.getenv("USER_ACCESS_TOKEN_AUDIENCE"),
            data,
            "user_access_token_audience",
        ),
        "incoming_service_token_audience": _get_from_env_or_yaml(
            env_name,
            os.getenv("INCOMING_SERVICE_TOKEN_AUDIENCE"),
            data,
            "incoming_service_token_audience",
        ),
        "allowed_caller_service_ids": _as_non_empty_str_list(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("ALLOWED_CALLER_SERVICE_IDS"),
                data,
                "allowed_caller_service_ids",
            )
        ),
        "service_id": _get_from_env_or_yaml(env_name, os.getenv("SERVICE_ID"), data, "service_id"),
        "service_private_key_path": service_private_key_path,
        "service_token_audience": _get_from_env_or_yaml(
            env_name,
            os.getenv("SERVICE_TOKEN_AUDIENCE"),
            data,
            "service_token_audience",
        ),
        "service_assertion_audience": _get_from_env_or_yaml(
            env_name,
            os.getenv("SERVICE_ASSERTION_AUDIENCE"),
            data,
            "service_assertion_audience",
        ),
        "service_assertion_ttl_seconds": int(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("SERVICE_ASSERTION_TTL_SECONDS"),
                data,
                "service_assertion_ttl_seconds",
            )
        ),
        "service_token_refresh_skew_seconds": int(
            _get_from_env_or_yaml(
                env_name,
                os.getenv("SERVICE_TOKEN_REFRESH_SKEW_SECONDS"),
                data,
                "service_token_refresh_skew_seconds",
            )
        ),
        "clock_skew_seconds": int(
            _get_from_env_or_yaml(env_name, os.getenv("CLOCK_SKEW_SECONDS"), data, "clock_skew_seconds")
        ),
    }

    return Settings(**_merge(data, env_overrides))
