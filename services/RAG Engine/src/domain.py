from dataclasses import dataclass


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
