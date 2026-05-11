from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from infrastructure.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _session_factory


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_schema() -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'open',
            updated_by TEXT,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            recipient_role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_events (
            id BIGSERIAL PRIMARY KEY,
            chat_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_status_history (
            id BIGSERIAL PRIMARY KEY,
            chat_id TEXT NOT NULL,
            status TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS operator_queue (
            queue_item_id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS specialist_queue (
            queue_item_id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            operator_id TEXT NOT NULL,
            note TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            decision TEXT,
            specialist_id TEXT,
            comment TEXT,
            reviewed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge_base_updates (
            id BIGSERIAL PRIMARY KEY,
            queue_item_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            specialist_id TEXT NOT NULL,
            comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_id ON chat_messages(chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_events_chat_id ON chat_events(chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_status_history_chat_id ON chat_status_history(chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_operator_queue_chat_id ON operator_queue(chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_specialist_queue_chat_id ON specialist_queue(chat_id)",
    ]
    with get_engine().begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
