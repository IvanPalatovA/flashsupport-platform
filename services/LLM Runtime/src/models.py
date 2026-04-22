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
