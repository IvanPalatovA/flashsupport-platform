from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from domain import SearchResultEntity


class SearchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, query_embedding: list[float], top_k: int) -> list[SearchResultEntity]:
        query_vector = "[" + ",".join(f"{value:.8f}" for value in query_embedding) + "]"
        sql = text(
            """
            SELECT
                c.id AS chunk_id,
                c.document_id AS document_id,
                d.title AS document_title,
                c.chunk_index AS chunk_index,
                1 - (c.embedding <=> CAST(:query_vector AS vector)) AS score,
                c.text AS text
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            ORDER BY c.embedding <=> CAST(:query_vector AS vector)
            LIMIT :top_k
            """
        )
        rows = self._session.execute(sql, {"query_vector": query_vector, "top_k": top_k}).mappings().all()
        return [
            SearchResultEntity(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_title=row["document_title"],
                chunk_index=row["chunk_index"],
                score=float(row["score"]),
                text=row["text"],
            )
            for row in rows
        ]
