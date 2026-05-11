from __future__ import annotations

import asyncio
import fnmatch
import json
import platform
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from infrastructure.config import Settings


class EmbeddingRuntimeError(RuntimeError):
    pass


class EmbeddingModelChangedError(EmbeddingRuntimeError):
    pass


@dataclass(slots=True)
class DownloadState:
    status: str = "idle"
    model_name: str | None = None
    huggingface_url: str | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    progress_percent: float = 0.0
    started_at: float | None = None
    updated_at: float | None = None
    error: str | None = None
    local_path: str | None = None


class EmbeddingRuntime:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._storage_dir = Path(settings.embedding_model_storage_dir).resolve()
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._registry_path = self._storage_dir / "registry.json"
        self._lock = threading.RLock()
        self._download_task: asyncio.Task[None] | None = None
        self._state = DownloadState()
        self._model: Any | None = None
        self._active_model_name: str | None = None
        self._active_model_path: str | None = None
        self._active_dimension: int | None = None
        self._active_device = self._resolve_device(settings.embedding_device)
        self._device_warning = self._build_device_warning(settings.embedding_device, self._active_device)
        self._generation = 0
        self._registry = self._load_registry()
        self._load_configured_default()

    _REQUIRED_PATTERNS = (
        "*.json",
        "*.txt",
        "1_Pooling/*",
        "2_Normalize/*",
    )
    _MODEL_FILE_PRIORITY = (
        "model.safetensors",
        "pytorch_model.bin",
    )

    def _now(self) -> float:
        return time.time()

    def _iso(self, ts: float | None) -> str | None:
        if ts is None:
            return None
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

    def _load_registry(self) -> dict[str, Any]:
        if not self._registry_path.exists():
            return {"active_model": None, "models": {}}
        try:
            payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"active_model": None, "models": {}}
        if not isinstance(payload, dict):
            return {"active_model": None, "models": {}}
        if not isinstance(payload.get("models"), dict):
            payload["models"] = {}
        return payload

    def _save_registry(self) -> None:
        self._registry_path.write_text(json.dumps(self._registry, indent=2, sort_keys=True), encoding="utf-8")

    def _sanitize_model_name(self, raw_name: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9._:/-]+", "-", raw_name.strip()).strip("-")
        if normalized == "":
            raise EmbeddingRuntimeError("model_name is empty after normalization")
        return normalized

    def _parse_hf_url(self, raw: str) -> str:
        value = raw.strip()
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            if parsed.netloc not in {"huggingface.co", "www.huggingface.co"}:
                raise EmbeddingRuntimeError("huggingface_url must point to huggingface.co")
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) < 2:
                raise EmbeddingRuntimeError("huggingface_url must include repository id")
            return "/".join(parts[:2])
        if "/" in value and len(value.split("/")) >= 2:
            return "/".join(value.split("/")[:2])
        raise EmbeddingRuntimeError("huggingface_url must be a Hugging Face repository URL or repo id")

    def _import_sentence_transformer(self) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise EmbeddingRuntimeError("sentence-transformers is not installed in RAG Engine") from error
        return SentenceTransformer

    def _resolve_device(self, requested_device: str) -> str:
        normalized = requested_device.strip().lower()
        if normalized == "":
            normalized = "auto"
        if normalized not in {"auto", "cuda", "mps", "cpu"}:
            raise EmbeddingRuntimeError("embedding_device must be one of: auto, cuda, mps, cpu")

        try:
            import torch
        except ImportError:
            if normalized in {"cuda", "mps"}:
                raise EmbeddingRuntimeError(f"embedding_device='{normalized}' requires torch")
            return "cpu"

        cuda_available = bool(torch.cuda.is_available())
        mps_available = bool(
            getattr(getattr(torch.backends, "mps", None), "is_available", lambda: False)()
        )

        if normalized == "cuda":
            return "cuda" if cuda_available else "cpu"
        if normalized == "mps":
            return "mps" if mps_available else "cpu"
        if normalized == "cpu":
            return "cpu"
        if cuda_available:
            return "cuda"
        if mps_available:
            return "mps"
        return "cpu"

    def _running_in_container(self) -> bool:
        if Path("/.dockerenv").exists():
            return True
        try:
            cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8")
        except OSError:
            return False
        return "docker" in cgroup or "containerd" in cgroup

    def _build_device_warning(self, requested_device: str, active_device: str) -> str | None:
        normalized = requested_device.strip().lower() or "auto"
        if active_device != "cpu":
            return None
        if normalized in {"cuda", "mps"}:
            return (
                f"Requested embedding_device='{normalized}', but that accelerator is not visible to this process; "
                "embedding runtime is using CPU fallback."
            )
        if self._running_in_container() and platform.system().lower() == "linux":
            return (
                "Embedding runtime is running inside a Linux Docker container. Docker Desktop on macOS does not expose "
                "Apple Metal/MPS to Linux containers; run RAG Engine natively on macOS for MPS acceleration."
            )
        if normalized == "cpu":
            return "Embedding runtime is forced to CPU; CUDA or Apple MPS acceleration is disabled."
        return "No CUDA or Apple MPS device was detected; embedding runtime is using CPU fallback."

    def _load_model_from_path(self, model_name: str, local_path: str) -> tuple[Any, int]:
        sentence_transformer = self._import_sentence_transformer()
        try:
            model = sentence_transformer(local_path, device=self._active_device)
            dimension = int(model.get_sentence_embedding_dimension())
        except Exception as error:
            raise EmbeddingRuntimeError(f"failed to load embedding model '{model_name}'") from error
        if dimension <= 0:
            raise EmbeddingRuntimeError(f"embedding model '{model_name}' returned invalid dimension")
        return model, dimension

    def _load_configured_default(self) -> None:
        default_model = self._settings.default_embedding_model
        active_model = self._registry.get("active_model")
        selected = str(active_model or default_model or "").strip()
        if selected == "":
            return
        models = self._registry.get("models", {})
        if selected not in models and default_model:
            try:
                self._download_worker(
                    huggingface_url=default_model,
                    token=None,
                    requested_model_name=default_model,
                    activate=True,
                )
            except Exception:
                return
            return
        info = models.get(selected) if isinstance(models, dict) else None
        if isinstance(info, dict) and isinstance(info.get("local_path"), str):
            try:
                self.activate_model(selected)
            except EmbeddingRuntimeError:
                return

    def _repo_files(self, repo_id: str, token: str | None) -> list[tuple[str, int]]:
        try:
            from huggingface_hub import HfApi
        except ImportError as error:
            raise EmbeddingRuntimeError("huggingface-hub is not installed in RAG Engine") from error

        try:
            info = HfApi().model_info(
                repo_id=repo_id,
                token=token.strip() if token and token.strip() else None,
                files_metadata=True,
            )
        except Exception as error:
            raise EmbeddingRuntimeError(f"failed to fetch Hugging Face model metadata for '{repo_id}'") from error

        files: list[tuple[str, int]] = []
        for sibling in info.siblings:
            filename = getattr(sibling, "rfilename", None)
            if not isinstance(filename, str) or filename == "":
                continue
            size_obj = getattr(sibling, "size", None)
            size = int(size_obj) if isinstance(size_obj, int) and size_obj > 0 else 0
            files.append((filename, size))
        return files

    def _select_download_files(self, repo_files: list[tuple[str, int]]) -> list[tuple[str, int]]:
        by_name = {name: size for name, size in repo_files}
        selected: dict[str, int] = {}

        for name, size in repo_files:
            if any(fnmatch.fnmatch(name, pattern) for pattern in self._REQUIRED_PATTERNS):
                selected[name] = size

        for model_file in self._MODEL_FILE_PRIORITY:
            if model_file in by_name:
                selected[model_file] = by_name[model_file]
                break
        else:
            raise EmbeddingRuntimeError("Hugging Face repository has no supported model weights file")

        ignored_prefixes = ("onnx/", "openvino/")
        ignored_names = {"tf_model.h5", "rust_model.ot", "flax_model.msgpack"}
        return sorted(
            (
                (name, size)
                for name, size in selected.items()
                if not name.startswith(ignored_prefixes) and Path(name).name not in ignored_names
            ),
            key=lambda item: item[0],
        )

    def _download_file(
        self,
        *,
        repo_id: str,
        revision: str,
        file_path: str,
        token: str | None,
        local_dir: Path,
        already_downloaded: int,
        total_bytes: int,
    ) -> int:
        local_file = local_dir / file_path
        local_file.parent.mkdir(parents=True, exist_ok=True)
        expected_size = total_bytes
        if local_file.exists() and local_file.stat().st_size > 0:
            return local_file.stat().st_size

        temp_file = local_file.with_suffix(local_file.suffix + ".part")
        headers: dict[str, str] = {}
        if token and token.strip() != "":
            headers["Authorization"] = f"Bearer {token.strip()}"

        url = f"https://huggingface.co/{repo_id}/resolve/{revision}/{file_path}"
        downloaded_for_file = 0
        try:
            with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=120.0) as response:
                response.raise_for_status()
                with temp_file.open("wb") as output:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        output.write(chunk)
                        downloaded_for_file += len(chunk)
                        downloaded_total = already_downloaded + downloaded_for_file
                        progress = 0.0 if expected_size <= 0 else min(100.0, downloaded_total * 100.0 / expected_size)
                        self._set_state(
                            downloaded_bytes=downloaded_total,
                            total_bytes=expected_size,
                            progress_percent=progress,
                            updated_at=self._now(),
                        )
        except httpx.HTTPError as error:
            raise EmbeddingRuntimeError(f"failed to download '{file_path}' from Hugging Face") from error

        temp_file.replace(local_file)
        return downloaded_for_file

    def _download_sentence_transformer(self, repo_id: str, token: str | None, local_dir: Path) -> None:
        self._cleanup_unneeded_files(local_dir)
        repo_files = self._repo_files(repo_id=repo_id, token=token)
        selected_files = self._select_download_files(repo_files)
        total_bytes = sum(size for _, size in selected_files)
        self._set_state(total_bytes=total_bytes, progress_percent=0.0, updated_at=self._now())

        downloaded = 0
        for file_path, size in selected_files:
            downloaded += self._download_file(
                repo_id=repo_id,
                revision="main",
                file_path=file_path,
                token=token,
                local_dir=local_dir,
                already_downloaded=downloaded,
                total_bytes=total_bytes,
            )
            if size <= 0:
                total_bytes = max(total_bytes, downloaded)
            self._set_state(
                downloaded_bytes=downloaded,
                total_bytes=total_bytes,
                progress_percent=100.0 if total_bytes <= 0 else min(100.0, downloaded * 100.0 / total_bytes),
                updated_at=self._now(),
            )
        self._cleanup_unneeded_files(local_dir)

    def _cleanup_unneeded_files(self, local_dir: Path) -> None:
        for relative in ("onnx", "openvino", ".cache"):
            path = local_dir / relative
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        for filename in ("tf_model.h5", "rust_model.ot", "flax_model.msgpack"):
            path = local_dir / filename
            if path.exists():
                path.unlink(missing_ok=True)

    def _download_worker(
        self,
        *,
        huggingface_url: str,
        token: str | None,
        requested_model_name: str | None,
        activate: bool,
    ) -> None:
        try:
            repo_id = self._parse_hf_url(huggingface_url)
            fallback_name = repo_id.replace("/", "--")
            model_name = self._sanitize_model_name(requested_model_name or fallback_name)
            local_dir = self._storage_dir / model_name
            local_dir.mkdir(parents=True, exist_ok=True)
            self._set_state(model_name=model_name, local_path=str(local_dir), updated_at=self._now())
            self._download_sentence_transformer(repo_id=repo_id, token=token, local_dir=local_dir)
            model, dimension = self._load_model_from_path(model_name, str(local_dir))
            with self._lock:
                self._registry["models"][model_name] = {
                    "model_name": model_name,
                    "source": "huggingface",
                    "repo_id": repo_id,
                            "local_path": str(local_dir),
                            "embedding_dimension": dimension,
                            "device": self._active_device,
                            "created_at": self._iso(self._now()),
                        }
                if activate:
                    self._model = model
                    self._active_model_name = model_name
                    self._active_model_path = str(local_dir)
                    self._active_dimension = dimension
                    self._generation += 1
                    self._registry["active_model"] = model_name
                self._save_registry()
            self._set_state(status="completed", progress_percent=100.0, error=None, updated_at=self._now())
        except Exception as error:
            self._set_state(status="failed", error=str(error), updated_at=self._now())

    def _set_state(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._state, key, value)

    def get_download_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._state.status,
                "model_name": self._state.model_name,
                "huggingface_url": self._state.huggingface_url,
                "downloaded_bytes": self._state.downloaded_bytes,
                "total_bytes": self._state.total_bytes,
                "progress_percent": self._state.progress_percent,
                "started_at": self._iso(self._state.started_at),
                "updated_at": self._iso(self._state.updated_at),
                "error": self._state.error,
                "local_path": self._state.local_path,
            }

    async def start_download(
        self,
        *,
        huggingface_url: str,
        token: str | None,
        model_name: str | None,
        activate: bool,
    ) -> dict[str, Any]:
        with self._lock:
            if self._download_task and not self._download_task.done():
                raise EmbeddingRuntimeError("another embedding model download is already running")
            self._state = DownloadState(
                status="downloading",
                model_name=model_name.strip() if isinstance(model_name, str) and model_name.strip() else None,
                huggingface_url=huggingface_url.strip(),
                started_at=self._now(),
                updated_at=self._now(),
            )
        loop = asyncio.get_running_loop()
        self._download_task = loop.create_task(
            asyncio.to_thread(
                self._download_worker,
                huggingface_url=huggingface_url,
                token=token,
                requested_model_name=model_name,
                activate=activate,
            )
        )
        return self.get_download_status()

    def list_models(self) -> dict[str, Any]:
        with self._lock:
            models: list[dict[str, Any]] = []
            raw_models = self._registry.get("models", {})
            if isinstance(raw_models, dict):
                for model_name, info in raw_models.items():
                    if not isinstance(info, dict):
                        continue
                    models.append(
                        {
                            "model_name": str(model_name),
                            "active": model_name == self._active_model_name,
                            "source": str(info.get("source", "huggingface")),
                            "repo_id": str(info.get("repo_id", "")),
                            "local_path": str(info.get("local_path", "")),
                            "embedding_dimension": int(info.get("embedding_dimension", 0)),
                            "device": str(info.get("device", self._active_device)),
                            "device_warning": (
                                self._device_warning
                                if model_name == self._active_model_name and self._active_device == "cpu"
                                else None
                            ),
                            "created_at": info.get("created_at"),
                        }
                    )
            models.sort(key=lambda item: item["model_name"])
            return {
                "active_model": self._active_model_name,
                "active_dimension": self._active_dimension,
                "device": self._active_device,
                "device_warning": self._device_warning,
                "models": models,
                "download": self.get_download_status(),
            }

    def activate_model(self, model_name: str) -> dict[str, Any]:
        normalized = self._sanitize_model_name(model_name)
        raw_models = self._registry.get("models", {})
        info = raw_models.get(normalized) if isinstance(raw_models, dict) else None
        if not isinstance(info, dict) or not isinstance(info.get("local_path"), str):
            raise EmbeddingRuntimeError(f"embedding model '{normalized}' is not available")
        model, dimension = self._load_model_from_path(normalized, info["local_path"])
        with self._lock:
            self._model = model
            self._active_model_name = normalized
            self._active_model_path = info["local_path"]
            self._active_dimension = dimension
            self._generation += 1
            self._registry["active_model"] = normalized
            self._registry["models"][normalized]["embedding_dimension"] = dimension
            self._registry["models"][normalized]["device"] = self._active_device
            self._save_registry()
        return self.list_models()

    def active_model_name(self) -> str:
        with self._lock:
            if not self._active_model_name:
                raise EmbeddingRuntimeError("no active embedding model")
            return self._active_model_name

    def active_dimension(self) -> int:
        with self._lock:
            if not self._active_dimension:
                raise EmbeddingRuntimeError("no active embedding model")
            return self._active_dimension

    def encode(self, text: str) -> tuple[list[float], str, int, int]:
        with self._lock:
            if self._model is None or not self._active_model_name or not self._active_dimension:
                raise EmbeddingRuntimeError("no active embedding model")
            model = self._model
            model_name = self._active_model_name
            dimension = self._active_dimension
            generation = self._generation
        try:
            vector_obj = model.encode(text, normalize_embeddings=True)
        except Exception as error:
            raise EmbeddingRuntimeError("embedding model failed to encode text") from error
        with self._lock:
            if generation != self._generation:
                raise EmbeddingModelChangedError("embedding model changed while request was running")
        raw_vector = vector_obj.tolist() if hasattr(vector_obj, "tolist") else vector_obj
        vector = [float(value) for value in raw_vector]
        return vector, model_name, dimension, generation

    def assert_generation(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                raise EmbeddingModelChangedError("embedding model changed while request was running")
