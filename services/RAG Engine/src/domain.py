from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SearchResultEntity:
    chunk_id: int | str
    document_id: int | str
    document_title: str
    chunk_index: int
    score: float
    text: str


@dataclass(slots=True)
class GeneratedAnswerEntity:
    answer: str
    model: str


@dataclass(slots=True)
class KnowledgeBaseEntity:
    id: int
    name: str
    description: str | None
    embedding_model: str
    embedding_dimension: int
    is_active: bool
    document_count: int
    chunk_count: int
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(slots=True)
class KnowledgeDocumentEntity:
    id: int
    knowledge_base_id: int
    title: str
    source: str | None
    chunk_count: int
    metadata: dict[str, Any]
    created_at: str
