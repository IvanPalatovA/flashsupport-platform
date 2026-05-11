from __future__ import annotations

from typing import Any, cast

import httpx

from domain import GeneratedAnswerEntity, SearchResultEntity


class LlmRuntimeError(RuntimeError):
    pass


def _safe_json_object(response: httpx.Response) -> dict[str, Any]:
    if not response.content:
        return {}
    try:
        payload: Any = response.json()
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return cast(dict[str, Any], payload)


class LlmRuntimeRepository:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def infer(
        self,
        *,
        instruction: str,
        contexts: list[SearchResultEntity],
        user_token: str,
        service_token: str,
        service_name: str,
    ) -> GeneratedAnswerEntity:
        url = f"{self._base_url}/inference"

        payload = {
            "instruction": instruction,
            "contexts": [
                {
                    "chunk_id": item.chunk_id,
                    "document_id": item.document_id,
                    "document_title": item.document_title,
                    "chunk_index": item.chunk_index,
                    "score": item.score,
                    "text": item.text,
                }
                for item in contexts
            ],
        }

        try:
            response = httpx.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "X-Service-Authorization": f"Bearer {service_token}",
                    "X-Service-Name": service_name,
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            detail = "LLM Runtime request failed: /inference"
            if isinstance(error, httpx.HTTPStatusError):
                payload = _safe_json_object(error.response)
                upstream_detail = payload.get("detail")
                if isinstance(upstream_detail, str) and upstream_detail.strip() != "":
                    detail = f"{detail} ({error.response.status_code}: {upstream_detail.strip()})"
                else:
                    detail = f"{detail} ({error.response.status_code})"
            elif str(error).strip() != "":
                detail = f"{detail} ({str(error).strip()})"

            raise LlmRuntimeError(detail) from error

        data = _safe_json_object(response)

        answer = data.get("answer")
        if not isinstance(answer, str) or answer.strip() == "":
            raise LlmRuntimeError("LLM Runtime returned empty answer")

        raw_model = data.get("model")
        model = str(raw_model).strip() if raw_model is not None else ""
        if model == "":
            model = "unknown"

        return GeneratedAnswerEntity(answer=answer.strip(), model=model)
