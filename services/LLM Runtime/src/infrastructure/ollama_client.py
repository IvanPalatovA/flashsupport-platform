from __future__ import annotations

import json
import hashlib
import threading
from pathlib import Path
from typing import Any, Callable

import httpx

from domain import ContextChunkEntity
from infrastructure.config import Settings


class OllamaClientError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._timeout_seconds = settings.ollama_request_timeout_seconds
        self._active_model = settings.llm_model_name
        self._system_prompt_path = Path(settings.model_storage_dir).resolve() / "system_prompt.txt"
        self._system_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        self._system_prompt = self._load_system_prompt(settings.llm_system_prompt)
        self._requested_device = self._normalize_device(settings.llm_device)
        self._device = "gpu" if self._requested_device in {"cuda", "mps"} else self._requested_device
        self._model_lock = threading.RLock()

    def _load_system_prompt(self, default_prompt: str) -> str:
        try:
            prompt = self._system_prompt_path.read_text(encoding="utf-8").strip()
        except OSError:
            return default_prompt
        return prompt or default_prompt

    def _normalize_device(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "":
            normalized = "auto"
        if normalized not in {"auto", "cpu", "gpu", "cuda", "mps"}:
            raise OllamaClientError("llm_device must be one of: auto, cpu, gpu, cuda, mps")
        return normalized

    def get_active_model(self) -> str:
        with self._model_lock:
            return self._active_model

    def get_device(self) -> str:
        return self._requested_device

    def get_device_warning(self) -> str | None:
        if self._device == "cpu":
            return "LLM Runtime is forced to CPU; Ollama will not use GPU layers for inference."
        if self._requested_device == "auto":
            return "Ollama chooses CUDA, Metal/MPS, or CPU in its own process; this service cannot verify the actual accelerator."
        return None

    def get_system_prompt(self) -> str:
        with self._model_lock:
            return self._system_prompt

    def set_system_prompt(self, system_prompt: str) -> str:
        normalized = system_prompt.strip()
        if normalized == "":
            raise OllamaClientError("system prompt cannot be empty")
        if len(normalized) > 8000:
            raise OllamaClientError("system prompt cannot be longer than 8000 characters")
        with self._model_lock:
            self._system_prompt = normalized
            self._system_prompt_path.write_text(normalized, encoding="utf-8")
            return self._system_prompt

    def set_active_model(self, model_name: str) -> None:
        normalized = model_name.strip()
        if normalized == "":
            raise OllamaClientError("model name cannot be empty")
        with self._model_lock:
            self._active_model = normalized

    def list_models(self) -> list[str]:
        url = f"{self._base_url}/api/tags"
        try:
            response = httpx.get(url, timeout=self._timeout_seconds)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise OllamaClientError("failed to query ollama model list") from error

        payload: Any
        try:
            payload = response.json()
        except ValueError as error:
            raise OllamaClientError("ollama returned invalid model list payload") from error

        models_raw = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models_raw, list):
            return []

        names: list[str] = []
        for item in models_raw:
            if not isinstance(item, dict):
                continue
            name_obj = item.get("name") or item.get("model")
            if isinstance(name_obj, str) and name_obj.strip() != "":
                names.append(name_obj.strip())
        return names

    def _http_error_detail(self, error: httpx.HTTPError) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            response = error.response
            body = response.text.strip()
            if len(body) > 500:
                body = body[:500] + "..."
            if body:
                return f"HTTP {response.status_code}: {body}"
            return f"HTTP {response.status_code}"
        if isinstance(error, httpx.RequestError):
            return str(error)
        return error.__class__.__name__

    def stop_model(self, model_name: str) -> None:
        normalized = model_name.strip()
        if normalized == "":
            return
        url = f"{self._base_url}/api/stop"
        try:
            response = httpx.post(url, json={"model": normalized}, timeout=self._timeout_seconds)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise OllamaClientError(f"failed to stop running model '{normalized}'") from error

    def create_model_from_gguf(self, model_name: str, gguf_path: str, system_prompt: str) -> None:
        normalized_model = model_name.strip()
        normalized_path = gguf_path.strip()
        if normalized_model == "":
            raise OllamaClientError("model name cannot be empty")
        if normalized_path == "":
            raise OllamaClientError("gguf path cannot be empty")

        gguf_file = Path(normalized_path)
        if not gguf_file.exists() or not gguf_file.is_file():
            raise OllamaClientError(f"gguf file not found: {normalized_path}")

        digest_hash = hashlib.sha256()
        with gguf_file.open("rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest_hash.update(chunk)
        digest = f"sha256:{digest_hash.hexdigest()}"

        blob_url = f"{self._base_url}/api/blobs/{digest}"
        try:
            with gguf_file.open("rb") as source:
                upload_response = httpx.post(
                    blob_url,
                    content=source,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=None,
                )
                upload_response.raise_for_status()
        except httpx.HTTPError as error:
            detail = self._http_error_detail(error)
            raise OllamaClientError(
                f"failed to upload GGUF blob to ollama for model '{normalized_model}': {detail}"
            ) from error

        modelfile = f'FROM {gguf_file.name}\nSYSTEM """\n{system_prompt.strip()}\n"""\n'
        create_url = f"{self._base_url}/api/create"
        try:
            create_response = httpx.post(
                create_url,
                json={
                    "model": normalized_model,
                    "modelfile": modelfile,
                    "files": {gguf_file.name: digest},
                    "stream": False,
                },
                timeout=max(600.0, self._timeout_seconds),
            )
            create_response.raise_for_status()
        except httpx.HTTPError as error:
            detail = self._http_error_detail(error)
            raise OllamaClientError(f"failed to register model '{normalized_model}' in ollama: {detail}") from error

    def _build_user_prompt(self, instruction: str, contexts: list[ContextChunkEntity]) -> str:
        lines = [f"Instruction:\n{instruction.strip()}", ""]

        if not contexts:
            lines.append("Retrieved context snippets: none")
            lines.append("Answer conservatively and explicitly say that context is insufficient if needed.")
            return "\n".join(lines)

        lines.append("Retrieved context snippets (top-k):")
        for index, item in enumerate(contexts, start=1):
            lines.extend(
                [
                    f"[{index}] title={item.document_title}; chunk_index={item.chunk_index}; score={item.score:.4f}",
                    item.text,
                    "",
                ]
            )

        lines.append("Use only relevant information from snippets. If snippets are insufficient, say that directly.")
        return "\n".join(lines)

    def _infer_generate_fallback(
        self,
        *,
        target_model: str,
        prompt: str,
        options: dict[str, float | int],
    ) -> tuple[str, str]:
        payload = {
            "model": target_model,
            "prompt": f"{self.get_system_prompt().strip()}\n\n{prompt}",
            "options": options,
            "stream": False,
        }
        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise OllamaClientError(f"ollama generate fallback failed: {self._http_error_detail(error)}") from error

        try:
            data = response.json()
        except ValueError as error:
            raise OllamaClientError("ollama generate fallback returned invalid JSON") from error
        if not isinstance(data, dict):
            raise OllamaClientError("ollama generate fallback returned invalid payload")
        answer_obj = data.get("response")
        answer = answer_obj.strip() if isinstance(answer_obj, str) else ""
        if answer == "":
            return (
                "Не удалось получить непустой ответ от LLM. Попробуйте переформулировать вопрос или выбрать другую модель.",
                target_model,
            )
        model_obj = data.get("model")
        model = model_obj.strip() if isinstance(model_obj, str) and model_obj.strip() else target_model
        return answer, model

    def infer(
        self,
        *,
        instruction: str,
        contexts: list[ContextChunkEntity],
        temperature: float | None,
        top_p: float | None,
        max_tokens: int | None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[str, str]:
        final_temperature = temperature if temperature is not None else self._settings.llm_temperature
        final_top_p = top_p if top_p is not None else self._settings.llm_top_p
        final_max_tokens = max_tokens if max_tokens is not None else self._settings.llm_max_tokens
        target_model = self.get_active_model()

        options = {
            "temperature": final_temperature,
            "top_p": final_top_p,
            "num_predict": final_max_tokens,
        }
        if self._device == "cpu":
            options["num_gpu"] = 0

        user_prompt = self._build_user_prompt(instruction=instruction, contexts=contexts)
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            "options": options,
            "stream": True,
        }

        answer_parts: list[str] = []
        resolved_model = target_model
        try:
            with httpx.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout_seconds,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if should_cancel and should_cancel():
                        try:
                            self.stop_model(target_model)
                        except OllamaClientError:
                            pass
                        raise OllamaClientError("inference interrupted: active model was switched")
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    if isinstance(chunk.get("error"), str) and chunk["error"].strip() != "":
                        raise OllamaClientError(f"ollama request failed: {chunk['error'].strip()}")
                    model_obj = chunk.get("model")
                    if isinstance(model_obj, str) and model_obj.strip() != "":
                        resolved_model = model_obj.strip()
                    message_obj = chunk.get("message")
                    if isinstance(message_obj, dict):
                        content_obj = message_obj.get("content")
                        if isinstance(content_obj, str) and content_obj != "":
                            answer_parts.append(content_obj)
        except OllamaClientError:
            raise
        except Exception as error:
            raise OllamaClientError("ollama request failed") from error

        answer = "".join(answer_parts).strip()
        if answer == "":
            return self._infer_generate_fallback(target_model=target_model, prompt=user_prompt, options=options)
        return answer, resolved_model
