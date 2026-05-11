from __future__ import annotations

import math
import re
from typing import Any, Protocol

from domain import GeneratedAnswerEntity, KnowledgeBaseEntity, KnowledgeDocumentEntity, SearchResultEntity
from infrastructure.config import Settings
from infrastructure.embedding_runtime import EmbeddingModelChangedError, EmbeddingRuntime, EmbeddingRuntimeError
from infrastructure.knowledge_repository import KnowledgeRepository
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


class SearchCancelledError(RuntimeError):
    pass


class SearchService:
    def __init__(
        self,
        repository: SearchRepository,
        settings: Settings,
        llm_runtime: LLMRuntimePort | None = None,
        knowledge_repository: KnowledgeRepository | None = None,
        embedding_runtime: EmbeddingRuntime | None = None,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._llm_runtime = llm_runtime
        self._knowledge_repository = knowledge_repository
        self._embedding_runtime = embedding_runtime

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
        if self._knowledge_repository is not None and self._embedding_runtime is not None:
            try:
                query_embedding, model_name, _, generation = self._embedding_runtime.encode(query)
                active_base = self._knowledge_repository.get_active_base()
                if active_base is not None and (
                    active_base.embedding_model != model_name or active_base.embedding_dimension != len(query_embedding)
                ):
                    raise RuntimeError(
                        "active knowledge base was indexed with a different embedding model; "
                        "activate its embedding model or choose another knowledge base"
                    )
                results = self._knowledge_repository.search_active(query_embedding=query_embedding, top_k=final_top_k)
                self._embedding_runtime.assert_generation(generation)
                return results
            except EmbeddingModelChangedError as error:
                raise SearchCancelledError(str(error)) from error
            except EmbeddingRuntimeError as error:
                raise RuntimeError(str(error)) from error

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


class KnowledgeAdminService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        settings: Settings,
        embedding_runtime: EmbeddingRuntime,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._embedding_runtime = embedding_runtime

    def _chunk_text(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if normalized == "":
            return []
        chunk_size = self._settings.chunk_size_chars
        overlap = min(self._settings.chunk_overlap_chars, max(0, chunk_size - 1))
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(len(normalized), start + chunk_size)
            chunks.append(normalized[start:end].strip())
            if end >= len(normalized):
                break
            start = max(0, end - overlap)
        return [chunk for chunk in chunks if chunk]

    def list_bases(self) -> list[KnowledgeBaseEntity]:
        return self._repository.list_bases()

    def list_documents(self, knowledge_base_id: int) -> list[KnowledgeDocumentEntity]:
        return self._repository.list_documents(knowledge_base_id)

    def create_base(
        self,
        *,
        name: str,
        description: str | None,
        documents: list[dict[str, Any]],
        metadata: dict[str, Any],
        activate: bool,
    ) -> KnowledgeBaseEntity:
        model_name = self._embedding_runtime.active_model_name()
        dimension = self._embedding_runtime.active_dimension()
        base = self._repository.create_base(
            name=name,
            description=description,
            embedding_model=model_name,
            embedding_dimension=dimension,
            metadata=metadata,
            activate=activate,
        )
        for document in documents:
            self.add_document(
                knowledge_base_id=base.id,
                title=str(document["title"]),
                text=str(document["text"]),
                source=document.get("source") if isinstance(document.get("source"), str) else None,
                metadata=document.get("metadata") if isinstance(document.get("metadata"), dict) else {},
            )
        return self._repository.get_base(base.id)

    def activate_base(self, knowledge_base_id: int) -> KnowledgeBaseEntity:
        return self._repository.activate_base(knowledge_base_id)

    def delete_base(self, knowledge_base_id: int) -> None:
        self._repository.delete_base(knowledge_base_id)

    def add_document(
        self,
        *,
        knowledge_base_id: int,
        title: str,
        text: str,
        source: str | None,
        metadata: dict[str, Any],
    ) -> KnowledgeDocumentEntity:
        base = self._repository.get_base(knowledge_base_id)
        active_model = self._embedding_runtime.active_model_name()
        active_dimension = self._embedding_runtime.active_dimension()
        if base.embedding_model != active_model or base.embedding_dimension != active_dimension:
            raise RuntimeError(
                "active embedding model must match the knowledge base embedding model before adding documents"
            )

        prepared_chunks: list[tuple[str, list[float], dict[str, Any]]] = []
        for chunk_index, chunk in enumerate(self._chunk_text(text)):
            embedding, _, _, generation = self._embedding_runtime.encode(chunk)
            self._embedding_runtime.assert_generation(generation)
            prepared_chunks.append((chunk, embedding, {"chunk_index": chunk_index}))
        if len(prepared_chunks) == 0:
            raise RuntimeError("document text produced no chunks")
        return self._repository.add_document(
            knowledge_base_id=knowledge_base_id,
            title=title,
            source=source,
            chunks=prepared_chunks,
            metadata=metadata,
        )

    def delete_document(self, knowledge_base_id: int, document_id: int) -> None:
        self._repository.delete_document(knowledge_base_id=knowledge_base_id, document_id=document_id)
