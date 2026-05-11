-- FlashSupport MVP Database Schema
-- pgvector extension disabled for MVP compatibility

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    collection TEXT NOT NULL DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks table (embedding as TEXT for MVP, can be upgraded to vector later)
CREATE TABLE IF NOT EXISTS chunks (
    doc_id TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding TEXT,  -- MVP: TEXT instead of vector(384)
    PRIMARY KEY (doc_id, chunk_index)
);

-- Simple B-tree index for MVP text search (replace with ivfflat when pgvector available)
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_text ON chunks USING gin(to_tsvector('english', text));

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    login TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','operator','specialist','system')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tokens table for JWT
CREATE TABLE IF NOT EXISTS tokens (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    token_type TEXT NOT NULL,
    token_value TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

-- Service keys for inter-service auth
CREATE TABLE IF NOT EXISTS service_keys (
    service_name TEXT PRIMARY KEY,
    public_key TEXT NOT NULL
);

-- Chats table
CREATE TABLE IF NOT EXISTS chats (
    chat_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','escalated','closed','blocked')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID REFERENCES chats(chat_id) ON DELETE CASCADE,
    sender_role TEXT NOT NULL CHECK (sender_role IN ('user','bot','operator','specialist')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Behavior events for proactive support (MVP)
CREATE TABLE IF NOT EXISTS behavior_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    page TEXT,
    idle_sec INT DEFAULT 0,
    back_count INT DEFAULT 0,
    form_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Learning queue for self-improvement (MVP)
CREATE TABLE IF NOT EXISTS learning_queue (
    queue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_answer TEXT NOT NULL,
    user_question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);


