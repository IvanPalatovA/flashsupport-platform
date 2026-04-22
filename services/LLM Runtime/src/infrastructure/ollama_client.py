from __future__ import annotations

from typing import Any

from ollama import Client, ResponseError

from domain import ContextChunkEntity
from infrastructure.config import Settings


class OllamaClientError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Client(
            host=settings.ollama_base_url,
            timeout=settings.ollama_request_timeout_seconds,
        )

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

    def _extract_content(self, response: Any) -> str:
        message_obj: Any
        if isinstance(response, dict):
            message_obj = response.get("message")
        else:
            message_obj = getattr(response, "message", None)

        content_obj: Any
        if isinstance(message_obj, dict):
            content_obj = message_obj.get("content")
        else:
            content_obj = getattr(message_obj, "content", None)

        if not isinstance(content_obj, str) or content_obj.strip() == "":
            raise OllamaClientError("ollama returned empty message content")

        return content_obj.strip()

    def _extract_model(self, response: Any) -> str:
        model_obj: Any
        if isinstance(response, dict):
            model_obj = response.get("model")
        else:
            model_obj = getattr(response, "model", None)

        if isinstance(model_obj, str) and model_obj.strip() != "":
            return model_obj
        return self._settings.llm_model_name

    def infer(
        self,
        *,
        instruction: str,
        contexts: list[ContextChunkEntity],
        temperature: float | None,
        top_p: float | None,
        max_tokens: int | None,
    ) -> tuple[str, str]:
        final_temperature = temperature if temperature is not None else self._settings.llm_temperature
        final_top_p = top_p if top_p is not None else self._settings.llm_top_p
        final_max_tokens = max_tokens if max_tokens is not None else self._settings.llm_max_tokens

        options = {
            "temperature": final_temperature,
            "top_p": final_top_p,
            "num_predict": final_max_tokens,
        }

        try:
            response = self._client.chat(
                model=self._settings.llm_model_name,
                messages=[
                    {"role": "system", "content": self._settings.llm_system_prompt},
                    {"role": "user", "content": self._build_user_prompt(instruction=instruction, contexts=contexts)},
                ],
                options=options,
                stream=False,
            )
        except ResponseError as error:
            raise OllamaClientError(f"ollama request failed: {error.error}") from error
        except Exception as error:
            raise OllamaClientError("ollama request failed") from error

        answer = self._extract_content(response)
        model = self._extract_model(response)
        return answer, model
