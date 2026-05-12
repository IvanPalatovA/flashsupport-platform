from __future__ import annotations

import asyncio
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from infrastructure.config import Settings
from infrastructure.ollama_client import OllamaClient, OllamaClientError


class ModelAdminError(RuntimeError):
    pass


@dataclass(slots=True)
class DownloadState:
    status: str = "idle"
    model_name: str | None = None
    huggingface_url: str | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    eta_seconds: int | None = None
    started_at: float | None = None
    updated_at: float | None = None
    error: str | None = None
    local_file: str | None = None


@dataclass(slots=True)
class RegisteredModel:
    local_file: str
    source: str
    model_format: str
    backend: str
    runnable: bool


class ModelAdminService:
    def __init__(
        self,
        settings: Settings,
        backend: OllamaClient,
        on_model_switched: Callable[..., None] | None = None,
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._on_model_switched = on_model_switched
        self._storage_dir = Path(settings.model_storage_dir).resolve()
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._download_task: asyncio.Task[None] | None = None
        self._state = DownloadState()
        self._registered_models: dict[str, RegisteredModel] = {}

    _SUPPORTED_FORMATS: dict[str, tuple[str, bool, str]] = {
        ".gguf": ("gguf", True, "ollama"),
        ".safetensors": ("safetensors", False, "manual"),
        ".bin": ("pytorch-bin", False, "manual"),
        ".pt": ("pytorch-pt", False, "manual"),
        ".pth": ("pytorch-pth", False, "manual"),
        ".onnx": ("onnx", False, "manual"),
        ".ggml": ("ggml", False, "manual"),
    }
    _FORMAT_PRIORITY: dict[str, int] = {
        "gguf": 100,
        "safetensors": 90,
        "pytorch-bin": 70,
        "onnx": 60,
        "pytorch-pt": 50,
        "pytorch-pth": 50,
        "ggml": 40,
    }

    def _now(self) -> float:
        return time.time()

    def _iso(self, ts: float | None) -> str | None:
        if ts is None:
            return None
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

    def _progress_percent(self, downloaded: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, downloaded * 100.0 / total))

    def _set_state(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._state, key, value)

    def get_download_status(self) -> dict[str, Any]:
        with self._lock:
            snapshot = DownloadState(
                status=self._state.status,
                model_name=self._state.model_name,
                huggingface_url=self._state.huggingface_url,
                downloaded_bytes=self._state.downloaded_bytes,
                total_bytes=self._state.total_bytes,
                eta_seconds=self._state.eta_seconds,
                started_at=self._state.started_at,
                updated_at=self._state.updated_at,
                error=self._state.error,
                local_file=self._state.local_file,
            )
        return {
            "status": snapshot.status,
            "model_name": snapshot.model_name,
            "huggingface_url": snapshot.huggingface_url,
            "downloaded_bytes": snapshot.downloaded_bytes,
            "total_bytes": snapshot.total_bytes,
            "progress_percent": self._progress_percent(snapshot.downloaded_bytes, snapshot.total_bytes),
            "eta_seconds": snapshot.eta_seconds,
            "started_at": self._iso(snapshot.started_at),
            "updated_at": self._iso(snapshot.updated_at),
            "error": snapshot.error,
            "local_file": snapshot.local_file,
        }

    def _sanitize_model_name(self, raw_name: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9._:/-]+", "-", raw_name.strip()).strip("-")
        if normalized == "":
            raise ModelAdminError("model_name is empty after normalization")
        return normalized

    def _parse_hf_url(self, huggingface_url: str) -> tuple[str, str, str | None]:
        parsed = urlparse(huggingface_url.strip())
        if parsed.scheme not in {"http", "https"} or parsed.netloc not in {"huggingface.co", "www.huggingface.co"}:
            raise ModelAdminError("huggingface_url must point to huggingface.co")

        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ModelAdminError("huggingface_url must include repository id")

        if "resolve" in parts:
            idx = parts.index("resolve")
            if idx < 2 or len(parts) <= idx + 1:
                raise ModelAdminError("invalid Hugging Face resolve URL format")
            repo_id = "/".join(parts[:idx])
            revision = parts[idx + 1]
            file_path = "/".join(parts[idx + 2 :]) if len(parts) > idx + 2 else None
            return repo_id, revision, file_path

        if "blob" in parts:
            idx = parts.index("blob")
            if idx < 2 or len(parts) <= idx + 1:
                raise ModelAdminError("invalid Hugging Face blob URL format")
            repo_id = "/".join(parts[:idx])
            revision = parts[idx + 1]
            file_path = "/".join(parts[idx + 2 :]) if len(parts) > idx + 2 else None
            return repo_id, revision, file_path

        if "tree" in parts:
            idx = parts.index("tree")
            if idx < 2 or len(parts) <= idx + 1:
                raise ModelAdminError("invalid Hugging Face tree URL format")
            repo_id = "/".join(parts[:idx])
            revision = parts[idx + 1]
            file_path = "/".join(parts[idx + 2 :]) if len(parts) > idx + 2 else None
            return repo_id, revision, file_path

        repo_id = "/".join(parts[:2])
        return repo_id, "main", None

    def _resolve_file_meta(self, file_path: str) -> tuple[str, bool, str]:
        lower = file_path.strip().lower()
        for extension, meta in self._SUPPORTED_FORMATS.items():
            if lower.endswith(extension):
                return meta
        raise ModelAdminError(
            "unsupported file format. Supported extensions: "
            + ", ".join(sorted(self._SUPPORTED_FORMATS.keys()))
        )

    def _resolve_repo_file(self, repo_id: str, revision: str, file_path: str | None, token: str | None) -> tuple[str, int, str]:
        headers: dict[str, str] = {}
        if token and token.strip() != "":
            headers["Authorization"] = f"Bearer {token.strip()}"

        if file_path and file_path.strip() != "":
            model_format, _, _ = self._resolve_file_meta(file_path.strip())
            return file_path.strip(), 0, model_format

        info_url = f"https://huggingface.co/api/models/{repo_id}"
        try:
            response = httpx.get(info_url, headers=headers, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ModelAdminError(f"failed to fetch model info from Hugging Face: {repo_id}") from error

        payload: Any
        try:
            payload = response.json()
        except ValueError as error:
            raise ModelAdminError("huggingface returned invalid model metadata payload") from error

        siblings = payload.get("siblings") if isinstance(payload, dict) else None
        if not isinstance(siblings, list):
            raise ModelAdminError("huggingface model metadata does not contain file list")

        candidates: list[tuple[str, int, str, int]] = []
        for item in siblings:
            if not isinstance(item, dict):
                continue
            rfilename = item.get("rfilename")
            if not isinstance(rfilename, str):
                continue
            try:
                model_format, _, _ = self._resolve_file_meta(rfilename)
            except ModelAdminError:
                continue
            size_obj = item.get("size")
            size = int(size_obj) if isinstance(size_obj, (int, float)) else 0
            priority = self._FORMAT_PRIORITY.get(model_format, 0)
            candidates.append((rfilename, max(0, size), model_format, priority))

        if len(candidates) == 0:
            raise ModelAdminError(
                f"repository '{repo_id}' has no supported model files. "
                "Supported extensions: "
                + ", ".join(sorted(self._SUPPORTED_FORMATS.keys()))
            )

        candidates.sort(key=lambda item: (item[3], item[1]), reverse=True)
        selected_file, selected_size, selected_format, _ = candidates[0]
        _ = revision
        return selected_file, selected_size, selected_format

    def _download_file(
        self,
        *,
        repo_id: str,
        revision: str,
        file_path: str,
        token: str | None,
        model_name: str,
        model_format: str,
    ) -> Path:
        headers: dict[str, str] = {}
        if token and token.strip() != "":
            headers["Authorization"] = f"Bearer {token.strip()}"

        download_url = f"https://huggingface.co/{repo_id}/resolve/{revision}/{file_path}"
        model_dir = self._storage_dir / repo_id.replace("/", "--")
        model_dir.mkdir(parents=True, exist_ok=True)
        local_file = model_dir / Path(file_path).name
        temp_file = local_file.with_suffix(local_file.suffix + ".part")

        self._set_state(local_file=str(local_file), updated_at=self._now())
        started_at = time.monotonic()
        downloaded_bytes = 0
        total_bytes = 0

        try:
            with httpx.stream(
                "GET",
                download_url,
                headers=headers,
                timeout=None,
                follow_redirects=True,
            ) as response:
                response.raise_for_status()
                content_len = response.headers.get("Content-Length")
                if content_len and content_len.isdigit():
                    total_bytes = int(content_len)
                self._set_state(total_bytes=total_bytes, updated_at=self._now())
                with temp_file.open("wb") as output:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        output.write(chunk)
                        downloaded_bytes += len(chunk)
                        elapsed = max(0.001, time.monotonic() - started_at)
                        speed = downloaded_bytes / elapsed
                        eta_seconds = None
                        if total_bytes > 0 and speed > 0:
                            eta_seconds = int(max(0.0, (total_bytes - downloaded_bytes) / speed))
                        self._set_state(
                            downloaded_bytes=downloaded_bytes,
                            total_bytes=total_bytes,
                            eta_seconds=eta_seconds,
                            updated_at=self._now(),
                        )
        except httpx.HTTPError as error:
            raise ModelAdminError("failed to download model file from Hugging Face") from error

        temp_file.replace(local_file)
        self._set_state(updated_at=self._now())

        _, runnable, backend = self._resolve_file_meta(file_path)
        if runnable:
            try:
                self._backend.create_model_from_gguf(
                    model_name=model_name,
                    gguf_path=str(local_file),
                    system_prompt=self._backend.get_system_prompt(),
                )
            except OllamaClientError as error:
                raise ModelAdminError(str(error)) from error

        with self._lock:
            self._registered_models[model_name] = RegisteredModel(
                local_file=str(local_file),
                source="huggingface",
                model_format=model_format,
                backend=backend,
                runnable=runnable,
            )

        return local_file

    def _download_worker(
        self,
        *,
        huggingface_url: str,
        token: str | None,
        requested_model_name: str | None,
    ) -> None:
        try:
            repo_id, revision, file_path = self._parse_hf_url(huggingface_url)
            resolved_file, guessed_size, resolved_format = self._resolve_repo_file(repo_id, revision, file_path, token)
            base_name = Path(resolved_file).stem
            fallback_name = f"{repo_id.replace('/', '--')}-{base_name}"
            model_name = self._sanitize_model_name(requested_model_name or fallback_name)
            self._set_state(model_name=model_name, total_bytes=guessed_size, updated_at=self._now())
            local_file = self._download_file(
                repo_id=repo_id,
                revision=revision,
                file_path=resolved_file,
                token=token,
                model_name=model_name,
                model_format=resolved_format,
            )
            self._set_state(
                status="completed",
                eta_seconds=0,
                error=None,
                local_file=str(local_file),
                updated_at=self._now(),
            )
        except Exception as error:
            self._set_state(status="failed", error=str(error), eta_seconds=None, updated_at=self._now())

    async def start_download(
        self,
        *,
        huggingface_url: str,
        token: str | None,
        model_name: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            if self._download_task and not self._download_task.done():
                raise ModelAdminError("another model download is already running")
            self._state = DownloadState(
                status="downloading",
                model_name=model_name.strip() if isinstance(model_name, str) and model_name.strip() != "" else None,
                huggingface_url=huggingface_url.strip(),
                downloaded_bytes=0,
                total_bytes=0,
                eta_seconds=None,
                started_at=self._now(),
                updated_at=self._now(),
                error=None,
                local_file=None,
            )

        loop = asyncio.get_running_loop()
        self._download_task = loop.create_task(
            asyncio.to_thread(
                self._download_worker,
                huggingface_url=huggingface_url,
                token=token,
                requested_model_name=model_name,
            )
        )
        return self.get_download_status()

    def list_models(self) -> dict[str, Any]:
        active_model = self._backend.get_active_model()
        try:
            ollama_models = self._backend.list_models()
        except OllamaClientError:
            # Keep admin panel usable even if Ollama is temporarily unavailable.
            ollama_models = []
        models: list[dict[str, Any]] = []
        seen = set()

        with self._lock:
            registered_copy = dict(self._registered_models)

        for model_name in ollama_models:
            local_model = registered_copy.get(model_name)
            models.append(
                {
                    "model_name": model_name,
                    "active": model_name == active_model,
                    "source": local_model.source if local_model else "ollama",
                    "local_file": local_model.local_file if local_model else None,
                    "model_format": local_model.model_format if local_model else "unknown",
                    "backend": local_model.backend if local_model else "ollama",
                    "runnable": local_model.runnable if local_model else True,
                }
            )
            seen.add(model_name)

        for model_name, local_model in registered_copy.items():
            if model_name in seen:
                continue
            models.append(
                {
                    "model_name": model_name,
                    "active": model_name == active_model,
                    "source": local_model.source,
                    "local_file": local_model.local_file,
                    "model_format": local_model.model_format,
                    "backend": local_model.backend,
                    "runnable": local_model.runnable,
                }
            )

        models.sort(key=lambda item: item["model_name"])
        return {
            "active_model": active_model,
            "device": self._backend.get_device(),
            "device_warning": self._backend.get_device_warning(),
            "models": models,
            "download": self.get_download_status(),
        }

    def activate_model(self, model_name: str) -> dict[str, Any]:
        normalized = self._sanitize_model_name(model_name)
        available_models = {item["model_name"]: item for item in self.list_models()["models"]}
        model_info = available_models.get(normalized)
        if model_info is None:
            raise ModelAdminError(f"model '{normalized}' is not available")
        if not bool(model_info.get("runnable", False)):
            raise ModelAdminError(
                f"model '{normalized}' is downloaded in '{model_info.get('model_format', 'unknown')}' format "
                "and cannot be activated in Ollama directly"
            )

        previous = self._backend.get_active_model()
        self._backend.set_active_model(normalized)

        if previous != normalized:
            try:
                self._backend.stop_model(previous)
            except OllamaClientError:
                pass
            if self._on_model_switched is not None:
                self._on_model_switched(previous_model=previous, new_model=normalized)

        return self.list_models()
