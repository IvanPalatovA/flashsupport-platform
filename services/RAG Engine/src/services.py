from __future__ import annotations

import math
import re
from typing import Protocol

from domain import GeneratedAnswerEntity, SearchResultEntity
from infrastructure.config import Settings
from infrastructure.search_repository import SearchRepository

_TOKEN_REGEX = re.compile(r"\w+", flags=re.UNICODE)


class LLMRuntimePort(Protocol):
    def infer(
        self,
        *,
        instruction: str,
        contexts: list[SearchResultEntity],
        user_token: str,
        service_token: str,
        service_name: str,
    ) -> GeneratedAnswerEntity:
        ...


class SearchService:
    def __init__(
        self,
        repository: SearchRepository,
        settings: Settings,
        llm_runtime: LLMRuntimePort | None = None,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._llm_runtime = llm_runtime

    def _embed(self, text: str) -> list[float]:
        # Lightweight local embedder for on-prem MVP; ingestion utility must use same dimension.
        vector = [0.0] * self._settings.vector_dimension
        tokens = _TOKEN_REGEX.findall(text.lower())
        if not tokens:
            return vector

        for token in tokens:
            idx = hash(token) % self._settings.vector_dimension
            vector[idx] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector

        return [value / norm for value in vector]

    def search(self, query: str, top_k: int | None = None) -> list[SearchResultEntity]:
        final_top_k = top_k or self._settings.default_top_k
        query_embedding = self._embed(query)
        return self._repository.search(query_embedding=query_embedding, top_k=final_top_k)

    def generate_answer(
        self,
        *,
        query: str,
        contexts: list[SearchResultEntity],
        user_token: str,
        service_token: str,
        service_name: str,
    ) -> GeneratedAnswerEntity:
        if self._llm_runtime is None:
            raise RuntimeError("LLM Runtime repository is not configured")

        return self._llm_runtime.infer(
            instruction=query,
            contexts=contexts,
            user_token=user_token,
            service_token=service_token,
            service_name=service_name,
        )
