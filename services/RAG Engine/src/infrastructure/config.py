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
    default_top_k: int
    vector_dimension: int = Field(ge=8)


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
        f"Missing required setting '{key}' for RAG_ENGINE_ENV='{env_name}'. "
        f"Set env var or define it in config/{env_name}.yaml or config/base.yaml"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    service_root = Path(__file__).resolve().parents[2]
    config_dir = service_root / "config"

    env_name = _required_env("RAG_ENGINE_ENV")
    env_config_path = config_dir / f"{env_name}.yaml"
    if not env_config_path.exists():
        raise FileNotFoundError(f"Environment config file not found: {env_config_path}")

    data = _merge(_read_yaml(config_dir / "base.yaml"), _read_yaml(env_config_path))

    env_overrides: dict[str, Any] = {
        "env": env_name,
        "app_name": _get_from_env_or_yaml(env_name, os.getenv("APP_NAME"), data, "app_name"),
        "host": _get_from_env_or_yaml(env_name, os.getenv("APP_HOST"), data, "host"),
        "port": int(_get_from_env_or_yaml(env_name, os.getenv("APP_PORT"), data, "port")),
        "log_level": _get_from_env_or_yaml(env_name, os.getenv("LOG_LEVEL"), data, "log_level"),
        "database_url": _get_from_env_or_yaml(env_name, os.getenv("DATABASE_URL"), data, "database_url"),
        "default_top_k": int(_get_from_env_or_yaml(env_name, os.getenv("DEFAULT_TOP_K"), data, "default_top_k")),
        "vector_dimension": int(
            _get_from_env_or_yaml(env_name, os.getenv("VECTOR_DIMENSION"), data, "vector_dimension")
        ),
    }

    return Settings(**_merge(data, env_overrides))
