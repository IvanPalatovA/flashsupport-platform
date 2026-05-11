from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from domain import KnowledgeBaseEntity, KnowledgeDocumentEntity, SearchResultEntity


def _json_object(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _base_from_row(self, row: Any) -> KnowledgeBaseEntity:
        return KnowledgeBaseEntity(
            id=int(row["id"]),
            name=str(row["name"]),
            description=row["description"],
            embedding_model=str(row["embedding_model"]),
            embedding_dimension=int(row["embedding_dimension"]),
            is_active=bool(row["is_active"]),
            document_count=int(row["document_count"]),
            chunk_count=int(row["chunk_count"]),
            metadata=_json_object(row["metadata"]),
            created_at=_iso(row["created_at"]),
            updated_at=_iso(row["updated_at"]),
        )

    def list_bases(self) -> list[KnowledgeBaseEntity]:
        rows = self._session.execute(
            text(
                """
                SELECT
                    kb.id,
                    kb.name,
                    kb.description,
                    kb.embedding_model,
                    kb.embedding_dimension,
                    kb.is_active,
                    kb.metadata,
                    kb.created_at,
                    kb.updated_at,
                    COUNT(DISTINCT kd.id) AS document_count,
                    COUNT(kc.id) AS chunk_count
                FROM knowledge_bases kb
                LEFT JOIN knowledge_documents kd ON kd.knowledge_base_id = kb.id
                LEFT JOIN knowledge_chunks kc ON kc.knowledge_base_id = kb.id
                GROUP BY kb.id
                ORDER BY kb.created_at DESC
                """
            )
        ).mappings().all()
        return [self._base_from_row(row) for row in rows]

    def get_active_base(self) -> KnowledgeBaseEntity | None:
        rows = self._session.execute(
            text(
                """
                SELECT
                    kb.id,
                    kb.name,
                    kb.description,
                    kb.embedding_model,
                    kb.embedding_dimension,
                    kb.is_active,
                    kb.metadata,
                    kb.created_at,
                    kb.updated_at,
                    COUNT(DISTINCT kd.id) AS document_count,
                    COUNT(kc.id) AS chunk_count
                FROM knowledge_bases kb
                LEFT JOIN knowledge_documents kd ON kd.knowledge_base_id = kb.id
                LEFT JOIN knowledge_chunks kc ON kc.knowledge_base_id = kb.id
                WHERE kb.is_active = TRUE
                GROUP BY kb.id
                ORDER BY kb.updated_at DESC
                LIMIT 1
                """
            )
        ).mappings().all()
        return self._base_from_row(rows[0]) if rows else None

    def create_base(
        self,
        *,
        name: str,
        description: str | None,
        embedding_model: str,
        embedding_dimension: int,
        metadata: dict[str, Any],
        activate: bool,
    ) -> KnowledgeBaseEntity:
        if activate:
            self._session.execute(text("UPDATE knowledge_bases SET is_active = FALSE WHERE is_active = TRUE"))
        row = self._session.execute(
            text(
                """
                INSERT INTO knowledge_bases (name, description, embedding_model, embedding_dimension, is_active, metadata)
                VALUES (:name, :description, :embedding_model, :embedding_dimension, :is_active, CAST(:metadata AS jsonb))
                RETURNING id
                """
            ),
            {
                "name": name,
                "description": description,
                "embedding_model": embedding_model,
                "embedding_dimension": embedding_dimension,
                "is_active": activate,
                "metadata": json.dumps(metadata),
            },
        ).mappings().one()
        self._session.commit()
        return self.get_base(int(row["id"]))

    def get_base(self, knowledge_base_id: int) -> KnowledgeBaseEntity:
        row = self._session.execute(
            text(
                """
                SELECT
                    kb.id,
                    kb.name,
                    kb.description,
                    kb.embedding_model,
                    kb.embedding_dimension,
                    kb.is_active,
                    kb.metadata,
                    kb.created_at,
                    kb.updated_at,
                    COUNT(DISTINCT kd.id) AS document_count,
                    COUNT(kc.id) AS chunk_count
                FROM knowledge_bases kb
                LEFT JOIN knowledge_documents kd ON kd.knowledge_base_id = kb.id
                LEFT JOIN knowledge_chunks kc ON kc.knowledge_base_id = kb.id
                WHERE kb.id = :id
                GROUP BY kb.id
                """
            ),
            {"id": knowledge_base_id},
        ).mappings().first()
        if row is None:
            raise ValueError(f"knowledge base '{knowledge_base_id}' not found")
        return self._base_from_row(row)

    def activate_base(self, knowledge_base_id: int) -> KnowledgeBaseEntity:
        self.get_base(knowledge_base_id)
        self._session.execute(text("UPDATE knowledge_bases SET is_active = FALSE WHERE is_active = TRUE"))
        self._session.execute(
            text("UPDATE knowledge_bases SET is_active = TRUE, updated_at = NOW() WHERE id = :id"),
            {"id": knowledge_base_id},
        )
        self._session.commit()
        return self.get_base(knowledge_base_id)

    def delete_base(self, knowledge_base_id: int) -> None:
        self.get_base(knowledge_base_id)
        self._session.execute(text("DELETE FROM knowledge_bases WHERE id = :id"), {"id": knowledge_base_id})
        self._session.commit()

    def add_document(
        self,
        *,
        knowledge_base_id: int,
        title: str,
        source: str | None,
        chunks: list[tuple[str, list[float], dict[str, Any]]],
        metadata: dict[str, Any],
    ) -> KnowledgeDocumentEntity:
        row = self._session.execute(
            text(
                """
                INSERT INTO knowledge_documents (knowledge_base_id, title, source, metadata)
                VALUES (:knowledge_base_id, :title, :source, CAST(:metadata AS jsonb))
                RETURNING id, created_at
                """
            ),
            {
                "knowledge_base_id": knowledge_base_id,
                "title": title,
                "source": source,
                "metadata": json.dumps(metadata),
            },
        ).mappings().one()
        document_id = int(row["id"])
        for index, (chunk_text, embedding, chunk_metadata) in enumerate(chunks):
            query_vector = "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
            self._session.execute(
                text(
                    """
                    INSERT INTO knowledge_chunks
                        (knowledge_base_id, document_id, chunk_index, text, embedding, metadata)
                    VALUES
                        (:knowledge_base_id, :document_id, :chunk_index, :text, CAST(:embedding AS vector), CAST(:metadata AS jsonb))
                    """
                ),
                {
                    "knowledge_base_id": knowledge_base_id,
                    "document_id": document_id,
                    "chunk_index": index,
                    "text": chunk_text,
                    "embedding": query_vector,
                    "metadata": json.dumps(chunk_metadata),
                },
            )
        self._session.execute(
            text("UPDATE knowledge_bases SET updated_at = NOW() WHERE id = :id"),
            {"id": knowledge_base_id},
        )
        self._session.commit()
        return KnowledgeDocumentEntity(
            id=document_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
            source=source,
            chunk_count=len(chunks),
            metadata=metadata,
            created_at=_iso(row["created_at"]),
        )

    def list_documents(self, knowledge_base_id: int) -> list[KnowledgeDocumentEntity]:
        rows = self._session.execute(
            text(
                """
                SELECT
                    kd.id,
                    kd.knowledge_base_id,
                    kd.title,
                    kd.source,
                    kd.metadata,
                    kd.created_at,
                    COUNT(kc.id) AS chunk_count
                FROM knowledge_documents kd
                LEFT JOIN knowledge_chunks kc ON kc.document_id = kd.id
                WHERE kd.knowledge_base_id = :knowledge_base_id
                GROUP BY kd.id
                ORDER BY kd.created_at DESC
                """
            ),
            {"knowledge_base_id": knowledge_base_id},
        ).mappings().all()
        return [
            KnowledgeDocumentEntity(
                id=int(row["id"]),
                knowledge_base_id=int(row["knowledge_base_id"]),
                title=str(row["title"]),
                source=row["source"],
                chunk_count=int(row["chunk_count"]),
                metadata=_json_object(row["metadata"]),
                created_at=_iso(row["created_at"]),
            )
            for row in rows
        ]

    def delete_document(self, knowledge_base_id: int, document_id: int) -> None:
        result = self._session.execute(
            text("DELETE FROM knowledge_documents WHERE knowledge_base_id = :knowledge_base_id AND id = :document_id"),
            {"knowledge_base_id": knowledge_base_id, "document_id": document_id},
        )
        if result.rowcount == 0:
            raise ValueError(f"document '{document_id}' not found")
        self._session.execute(
            text("UPDATE knowledge_bases SET updated_at = NOW() WHERE id = :id"),
            {"id": knowledge_base_id},
        )
        self._session.commit()

    def search_active(self, query_embedding: list[float], top_k: int) -> list[SearchResultEntity]:
        active = self.get_active_base()
        if active is None:
            return []
        query_vector = "[" + ",".join(f"{value:.8f}" for value in query_embedding) + "]"
        rows = self._session.execute(
            text(
                """
                SELECT
                    kc.id AS chunk_id,
                    kd.id AS document_id,
                    kd.title AS document_title,
                    kc.chunk_index AS chunk_index,
                    1 - (kc.embedding <=> CAST(:query_vector AS vector)) AS score,
                    kc.text AS text
                FROM knowledge_chunks kc
                JOIN knowledge_documents kd ON kd.id = kc.document_id
                WHERE kc.knowledge_base_id = :knowledge_base_id
                ORDER BY kc.embedding <=> CAST(:query_vector AS vector)
                LIMIT :top_k
                """
            ),
            {"query_vector": query_vector, "top_k": top_k, "knowledge_base_id": active.id},
        ).mappings().all()
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
