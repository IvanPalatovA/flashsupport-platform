from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    queue_depth: int = Field(ge=0)


class ContextChunk(BaseModel):
    chunk_id: int | str
    document_id: int | str
    document_title: str
    chunk_index: int
    score: float
    text: str = Field(min_length=1, max_length=12000)


class InferenceRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=8000)
    contexts: list[ContextChunk] = Field(default_factory=list, max_length=50)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, gt=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=16384)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class InferenceResponse(BaseModel):
    request_id: str
    model: str
    answer: str
    queue_wait_ms: int = Field(ge=0)
    inference_ms: int = Field(ge=0)


class RuntimeModel(BaseModel):
    model_name: str
    active: bool
    source: str
    local_file: str | None = None
    model_format: str = "unknown"
    backend: str = "ollama"
    runnable: bool = True


class DownloadStatusResponse(BaseModel):
    status: str
    model_name: str | None = None
    huggingface_url: str | None = None
    downloaded_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    progress_percent: float = Field(ge=0.0, le=100.0)
    eta_seconds: int | None = Field(default=None, ge=0)
    started_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
    local_file: str | None = None


class RuntimeModelsResponse(BaseModel):
    active_model: str
    device: str = "auto"
    device_warning: str | None = None
    models: list[RuntimeModel] = Field(default_factory=list)
    download: DownloadStatusResponse


class ModelDownloadRequest(BaseModel):
    huggingface_url: str = Field(min_length=10, max_length=2000)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    huggingface_token: str | None = Field(default=None, min_length=1, max_length=512)


class ModelActivateRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=128)
