from dataclasses import dataclass


@dataclass(slots=True)
class ContextChunkEntity:
    chunk_id: int | str
    document_id: int | str
    document_title: str
    chunk_index: int
    score: float
    text: str


@dataclass(slots=True)
class InferenceResultEntity:
    answer: str
    model: str
    queue_wait_ms: int
    inference_ms: int
