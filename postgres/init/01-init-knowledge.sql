-- Initialize separate logical database for Knowledge Base & Vector Storage
SELECT 'CREATE DATABASE knowledge_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'knowledge_db')\gexec

\c knowledge_db;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_collections (
    name TEXT PRIMARY KEY,
    vector_size INTEGER NOT NULL,
    distance TEXT NOT NULL DEFAULT 'Cosine',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id UUID PRIMARY KEY,
    collection_name TEXT NOT NULL REFERENCES kb_collections(name) ON DELETE CASCADE,
    document_id UUID NOT NULL,
    source TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_collection ON kb_chunks(collection_name);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_document ON kb_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_metadata ON kb_chunks USING gin(metadata);
