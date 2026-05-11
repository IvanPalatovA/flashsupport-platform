from pydantic import BaseModel, Field
from typing import Any


class HealthResponse(BaseModel):
    status: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)


class SearchResult(BaseModel):
    chunk_id: int | str
    document_id: int | str
    document_title: str
    chunk_index: int
    score: float
    text: str


class SearchResponse(BaseModel):
    query: str
    top_k: int
    results: list[SearchResult]
    generated_answer: str
    llm_model: str


class EmbeddingModel(BaseModel):
    model_name: str
    active: bool
    source: str
    repo_id: str
    local_path: str
    embedding_dimension: int = Field(ge=0)
    device: str = "cpu"
    device_warning: str | None = None
    created_at: str | None = None


class EmbeddingDownloadStatus(BaseModel):
    status: str
    model_name: str | None = None
    huggingface_url: str | None = None
    downloaded_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    progress_percent: float = Field(ge=0.0, le=100.0)
    started_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
    local_path: str | None = None


class EmbeddingModelsResponse(BaseModel):
    active_model: str | None = None
    active_dimension: int | None = Field(default=None, ge=1)
    device: str = "cpu"
    device_warning: str | None = None
    models: list[EmbeddingModel] = Field(default_factory=list)
    download: EmbeddingDownloadStatus


class EmbeddingModelDownloadRequest(BaseModel):
    huggingface_url: str = Field(min_length=2, max_length=2000)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    huggingface_token: str | None = Field(default=None, min_length=1, max_length=512)
    activate: bool = True


class EmbeddingModelActivateRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=128)


class KnowledgeDocumentInput(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=200000)
    source: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBase(BaseModel):
    id: int
    name: str
    description: str | None = None
    embedding_model: str
    embedding_dimension: int
    is_active: bool
    document_count: int
    chunk_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class KnowledgeDocument(BaseModel):
    id: int
    knowledge_base_id: int
    title: str
    source: str | None = None
    chunk_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class KnowledgeBasesResponse(BaseModel):
    bases: list[KnowledgeBase] = Field(default_factory=list)


class KnowledgeDocumentsResponse(BaseModel):
    documents: list[KnowledgeDocument] = Field(default_factory=list)


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    documents: list[KnowledgeDocumentInput] = Field(default_factory=list, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    activate: bool = True


class KnowledgeDocumentCreateRequest(KnowledgeDocumentInput):
    pass
