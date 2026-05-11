from pydantic import BaseModel, Field


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
