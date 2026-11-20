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

CREATE TABLE IF NOT EXISTS flow_schedules (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    flow_type TEXT NOT NULL,
    connector_type TEXT NOT NULL DEFAULT 'email_imap',
    interval_minutes INTEGER NOT NULL DEFAULT 15,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_run_at TIMESTAMPTZ,
    last_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS flow_runs (
    id UUID PRIMARY KEY,
    schedule_id UUID REFERENCES flow_schedules(id) ON DELETE SET NULL,
    schedule_name TEXT NOT NULL,
    flow_type TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flow_runs_executed_at ON flow_runs(executed_at DESC);
