-- =============================================================================
-- pgvector Setup Script
-- Purpose: Set up PostgreSQL with pgvector extension for RAG vector storage.
--          Creates embeddings tables, HNSW indexes, full-text search indexes,
--          and supporting functions.
-- Platform: Azure Database for PostgreSQL Flexible Server
-- Prerequisites: PostgreSQL 15+ with pgvector extension available
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Step 1: Enable Extensions
-- ---------------------------------------------------------------------------

-- pgvector for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- pg_trgm for trigram-based similarity (fuzzy keyword matching)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- uuid-ossp for generating UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify pgvector is installed
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension is not installed. Please install it first.';
    END IF;
    RAISE NOTICE 'pgvector extension verified.';
END $$;


-- ---------------------------------------------------------------------------
-- Step 2: Create Embeddings Tables
-- ---------------------------------------------------------------------------

-- Primary product catalog embeddings table
CREATE TABLE IF NOT EXISTS product_catalog_embeddings (
    id                  TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL,
    source_file         TEXT,
    content             TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,
    chunk_index         INTEGER DEFAULT 0,
    total_chunks        INTEGER DEFAULT 1,
    embedding           vector(1536),           -- text-embedding-3-large default dimensions
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Add generated tsvector column for full-text search
ALTER TABLE product_catalog_embeddings
ADD COLUMN IF NOT EXISTS content_tsv tsvector
GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

COMMENT ON TABLE product_catalog_embeddings IS
    'Product catalog document embeddings for RAG retrieval. '
    'Uses text-embedding-3-large (1536 dimensions) from Azure OpenAI.';

COMMENT ON COLUMN product_catalog_embeddings.embedding IS
    'Dense vector embedding from Azure OpenAI text-embedding-3-large model.';
COMMENT ON COLUMN product_catalog_embeddings.content_tsv IS
    'Auto-generated tsvector for PostgreSQL full-text search (keyword matching).';
COMMENT ON COLUMN product_catalog_embeddings.metadata IS
    'JSONB metadata: material_number, product_name, category, document_type, etc.';


-- General-purpose embeddings table for other document types
-- (e.g., historical analysis reports, planning documents)
CREATE TABLE IF NOT EXISTS document_embeddings (
    id                  TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL,
    source_file         TEXT,
    content             TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    document_type       TEXT NOT NULL,           -- 'analysis_report', 'planning_doc', etc.
    metadata            JSONB DEFAULT '{}'::jsonb,
    chunk_index         INTEGER DEFAULT 0,
    total_chunks        INTEGER DEFAULT 1,
    embedding           vector(1536),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE document_embeddings
ADD COLUMN IF NOT EXISTS content_tsv tsvector
GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

COMMENT ON TABLE document_embeddings IS
    'General-purpose document embeddings for non-product documents (reports, analyses).';


-- ---------------------------------------------------------------------------
-- Step 3: Create Indexes
-- ---------------------------------------------------------------------------

-- HNSW indexes for approximate nearest neighbor search
-- HNSW provides better recall than IVFFlat for most workloads
-- m=16: number of bi-directional links per node (higher = better recall, more memory)
-- ef_construction=200: size of dynamic candidate list during index build (higher = better quality)

-- Product catalog HNSW index (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_product_catalog_embedding_hnsw
ON product_catalog_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- Document embeddings HNSW index
CREATE INDEX IF NOT EXISTS idx_document_embedding_hnsw
ON document_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- Full-text search GIN indexes
CREATE INDEX IF NOT EXISTS idx_product_catalog_fts
ON product_catalog_embeddings
USING gin (content_tsv);

CREATE INDEX IF NOT EXISTS idx_document_fts
ON document_embeddings
USING gin (content_tsv);

-- JSONB metadata GIN indexes for filtered queries
CREATE INDEX IF NOT EXISTS idx_product_catalog_metadata_gin
ON product_catalog_embeddings
USING gin (metadata jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_document_metadata_gin
ON document_embeddings
USING gin (metadata jsonb_path_ops);

-- B-tree indexes for common lookup patterns
CREATE INDEX IF NOT EXISTS idx_product_catalog_doc_id
ON product_catalog_embeddings (document_id);

CREATE INDEX IF NOT EXISTS idx_product_catalog_content_hash
ON product_catalog_embeddings (content_hash);

CREATE INDEX IF NOT EXISTS idx_document_doc_id
ON document_embeddings (document_id);

CREATE INDEX IF NOT EXISTS idx_document_type
ON document_embeddings (document_type);

-- Trigram index for fuzzy text matching
CREATE INDEX IF NOT EXISTS idx_product_catalog_content_trgm
ON product_catalog_embeddings
USING gin (content gin_trgm_ops);


-- ---------------------------------------------------------------------------
-- Step 4: Configure HNSW Search Parameters
-- ---------------------------------------------------------------------------

-- Set search-time ef parameter (higher = better recall, slower search)
-- Default is 40; increase for better accuracy at the cost of latency
ALTER SYSTEM SET hnsw.ef_search = 100;
SELECT pg_reload_conf();


-- ---------------------------------------------------------------------------
-- Step 5: Helper Functions
-- ---------------------------------------------------------------------------

-- Function: Semantic search (cosine similarity)
CREATE OR REPLACE FUNCTION search_product_catalog_semantic(
    query_embedding vector(1536),
    match_count INTEGER DEFAULT 5,
    min_similarity FLOAT DEFAULT 0.3,
    metadata_filter JSONB DEFAULT NULL
)
RETURNS TABLE (
    id TEXT,
    document_id TEXT,
    content TEXT,
    metadata JSONB,
    source_file TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        pce.id,
        pce.document_id,
        pce.content,
        pce.metadata,
        pce.source_file,
        (1 - (pce.embedding <=> query_embedding))::FLOAT AS similarity
    FROM product_catalog_embeddings pce
    WHERE
        (metadata_filter IS NULL OR pce.metadata @> metadata_filter)
        AND (1 - (pce.embedding <=> query_embedding)) >= min_similarity
    ORDER BY pce.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION search_product_catalog_semantic IS
    'Perform semantic (vector) search on product catalog embeddings. '
    'Returns top-k results sorted by cosine similarity.';


-- Function: Full-text keyword search
CREATE OR REPLACE FUNCTION search_product_catalog_keyword(
    search_query TEXT,
    match_count INTEGER DEFAULT 5,
    metadata_filter JSONB DEFAULT NULL
)
RETURNS TABLE (
    id TEXT,
    document_id TEXT,
    content TEXT,
    metadata JSONB,
    source_file TEXT,
    rank_score FLOAT
)
LANGUAGE plpgsql
AS $$
DECLARE
    tsquery_val tsquery;
BEGIN
    -- Convert search query to tsquery with OR for flexibility
    tsquery_val := plainto_tsquery('english', search_query);

    RETURN QUERY
    SELECT
        pce.id,
        pce.document_id,
        pce.content,
        pce.metadata,
        pce.source_file,
        ts_rank_cd(pce.content_tsv, tsquery_val)::FLOAT AS rank_score
    FROM product_catalog_embeddings pce
    WHERE
        pce.content_tsv @@ tsquery_val
        AND (metadata_filter IS NULL OR pce.metadata @> metadata_filter)
    ORDER BY rank_score DESC
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION search_product_catalog_keyword IS
    'Perform full-text keyword search on product catalog. '
    'Uses PostgreSQL tsvector for efficient text matching.';


-- Function: Hybrid search with Reciprocal Rank Fusion (RRF)
CREATE OR REPLACE FUNCTION search_product_catalog_hybrid(
    query_embedding vector(1536),
    search_query TEXT,
    match_count INTEGER DEFAULT 5,
    semantic_weight FLOAT DEFAULT 0.7,
    keyword_weight FLOAT DEFAULT 0.3,
    rrf_k INTEGER DEFAULT 60,
    metadata_filter JSONB DEFAULT NULL
)
RETURNS TABLE (
    id TEXT,
    document_id TEXT,
    content TEXT,
    metadata JSONB,
    source_file TEXT,
    semantic_score FLOAT,
    keyword_score FLOAT,
    combined_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH semantic_results AS (
        SELECT
            s.id,
            s.document_id,
            s.content,
            s.metadata,
            s.source_file,
            s.similarity AS sem_score,
            ROW_NUMBER() OVER (ORDER BY s.similarity DESC) AS sem_rank
        FROM search_product_catalog_semantic(
            query_embedding, match_count * 3, 0.1, metadata_filter
        ) s
    ),
    keyword_results AS (
        SELECT
            k.id,
            k.document_id,
            k.content,
            k.metadata,
            k.source_file,
            k.rank_score AS kw_score,
            ROW_NUMBER() OVER (ORDER BY k.rank_score DESC) AS kw_rank
        FROM search_product_catalog_keyword(
            search_query, match_count * 3, metadata_filter
        ) k
    ),
    combined AS (
        SELECT
            COALESCE(s.id, k.id) AS id,
            COALESCE(s.document_id, k.document_id) AS document_id,
            COALESCE(s.content, k.content) AS content,
            COALESCE(s.metadata, k.metadata) AS metadata,
            COALESCE(s.source_file, k.source_file) AS source_file,
            COALESCE(s.sem_score, 0)::FLOAT AS semantic_score,
            COALESCE(k.kw_score, 0)::FLOAT AS keyword_score,
            (
                COALESCE(semantic_weight / (rrf_k + s.sem_rank), 0) +
                COALESCE(keyword_weight / (rrf_k + k.kw_rank), 0)
            )::FLOAT AS combined_score
        FROM semantic_results s
        FULL OUTER JOIN keyword_results k ON s.id = k.id
    )
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.metadata,
        c.source_file,
        c.semantic_score,
        c.keyword_score,
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION search_product_catalog_hybrid IS
    'Hybrid search combining semantic (vector) and keyword (full-text) search '
    'using Reciprocal Rank Fusion (RRF) for score combination.';


-- ---------------------------------------------------------------------------
-- Step 5b: Document Embeddings Search Functions
-- Used for equipment health, customer 360, and other non-product documents
-- ---------------------------------------------------------------------------

-- Function: Semantic search on document_embeddings
CREATE OR REPLACE FUNCTION search_documents_semantic(
    query_embedding vector(1536),
    match_count INTEGER DEFAULT 5,
    min_similarity FLOAT DEFAULT 0.3,
    document_type_filter TEXT DEFAULT NULL,
    metadata_filter JSONB DEFAULT NULL
)
RETURNS TABLE (
    id TEXT,
    document_id TEXT,
    content TEXT,
    document_type TEXT,
    metadata JSONB,
    source_file TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        de.id,
        de.document_id,
        de.content,
        de.document_type,
        de.metadata,
        de.source_file,
        (1 - (de.embedding <=> query_embedding))::FLOAT AS similarity
    FROM document_embeddings de
    WHERE
        (document_type_filter IS NULL OR de.document_type = document_type_filter)
        AND (metadata_filter IS NULL OR de.metadata @> metadata_filter)
        AND (1 - (de.embedding <=> query_embedding)) >= min_similarity
    ORDER BY de.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION search_documents_semantic IS
    'Semantic search on document_embeddings with optional document_type filter. '
    'Use document_type_filter=''equipment_health'' for predictive maintenance queries.';


-- Function: Full-text keyword search on document_embeddings
CREATE OR REPLACE FUNCTION search_documents_keyword(
    search_query TEXT,
    match_count INTEGER DEFAULT 5,
    document_type_filter TEXT DEFAULT NULL,
    metadata_filter JSONB DEFAULT NULL
)
RETURNS TABLE (
    id TEXT,
    document_id TEXT,
    content TEXT,
    document_type TEXT,
    metadata JSONB,
    source_file TEXT,
    rank_score FLOAT
)
LANGUAGE plpgsql
AS $$
DECLARE
    tsquery_val tsquery;
BEGIN
    tsquery_val := plainto_tsquery('english', search_query);

    RETURN QUERY
    SELECT
        de.id,
        de.document_id,
        de.content,
        de.document_type,
        de.metadata,
        de.source_file,
        ts_rank_cd(de.content_tsv, tsquery_val)::FLOAT AS rank_score
    FROM document_embeddings de
    WHERE
        de.content_tsv @@ tsquery_val
        AND (document_type_filter IS NULL OR de.document_type = document_type_filter)
        AND (metadata_filter IS NULL OR de.metadata @> metadata_filter)
    ORDER BY rank_score DESC
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION search_documents_keyword IS
    'Full-text keyword search on document_embeddings with optional document_type filter.';


-- Function: Hybrid search on document_embeddings with RRF
CREATE OR REPLACE FUNCTION search_documents_hybrid(
    query_embedding vector(1536),
    search_query TEXT,
    match_count INTEGER DEFAULT 5,
    semantic_weight FLOAT DEFAULT 0.7,
    keyword_weight FLOAT DEFAULT 0.3,
    rrf_k INTEGER DEFAULT 60,
    document_type_filter TEXT DEFAULT NULL,
    metadata_filter JSONB DEFAULT NULL
)
RETURNS TABLE (
    id TEXT,
    document_id TEXT,
    content TEXT,
    document_type TEXT,
    metadata JSONB,
    source_file TEXT,
    semantic_score FLOAT,
    keyword_score FLOAT,
    combined_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH semantic_results AS (
        SELECT
            s.id,
            s.document_id,
            s.content,
            s.document_type,
            s.metadata,
            s.source_file,
            s.similarity AS sem_score,
            ROW_NUMBER() OVER (ORDER BY s.similarity DESC) AS sem_rank
        FROM search_documents_semantic(
            query_embedding, match_count * 3, 0.1, document_type_filter, metadata_filter
        ) s
    ),
    keyword_results AS (
        SELECT
            k.id,
            k.document_id,
            k.content,
            k.document_type,
            k.metadata,
            k.source_file,
            k.rank_score AS kw_score,
            ROW_NUMBER() OVER (ORDER BY k.rank_score DESC) AS kw_rank
        FROM search_documents_keyword(
            search_query, match_count * 3, document_type_filter, metadata_filter
        ) k
    ),
    combined AS (
        SELECT
            COALESCE(s.id, k.id) AS id,
            COALESCE(s.document_id, k.document_id) AS document_id,
            COALESCE(s.content, k.content) AS content,
            COALESCE(s.document_type, k.document_type) AS document_type,
            COALESCE(s.metadata, k.metadata) AS metadata,
            COALESCE(s.source_file, k.source_file) AS source_file,
            COALESCE(s.sem_score, 0)::FLOAT AS semantic_score,
            COALESCE(k.kw_score, 0)::FLOAT AS keyword_score,
            (
                COALESCE(semantic_weight / (rrf_k + s.sem_rank), 0) +
                COALESCE(keyword_weight / (rrf_k + k.kw_rank), 0)
            )::FLOAT AS combined_score
        FROM semantic_results s
        FULL OUTER JOIN keyword_results k ON s.id = k.id
    )
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.document_type,
        c.metadata,
        c.source_file,
        c.semantic_score,
        c.keyword_score,
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION search_documents_hybrid IS
    'Hybrid search on document_embeddings combining semantic and keyword search '
    'with RRF scoring. Filter by document_type (e.g., equipment_health, customer_360).';


-- ---------------------------------------------------------------------------
-- Step 6: Maintenance Functions
-- ---------------------------------------------------------------------------

-- Function: Get index statistics
CREATE OR REPLACE FUNCTION get_embedding_stats()
RETURNS TABLE (
    table_name TEXT,
    total_chunks BIGINT,
    total_documents BIGINT,
    avg_content_length FLOAT,
    oldest_record TIMESTAMPTZ,
    newest_record TIMESTAMPTZ
)
LANGUAGE sql
AS $$
    SELECT
        'product_catalog_embeddings'::TEXT,
        COUNT(*),
        COUNT(DISTINCT document_id),
        AVG(LENGTH(content))::FLOAT,
        MIN(created_at),
        MAX(updated_at)
    FROM product_catalog_embeddings
    UNION ALL
    SELECT
        'document_embeddings'::TEXT,
        COUNT(*),
        COUNT(DISTINCT document_id),
        AVG(LENGTH(content))::FLOAT,
        MIN(created_at),
        MAX(updated_at)
    FROM document_embeddings;
$$;


-- Function: Clean up orphaned chunks (chunks whose documents have been reindexed)
CREATE OR REPLACE FUNCTION cleanup_stale_embeddings(
    max_age_days INTEGER DEFAULT 30
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM product_catalog_embeddings
    WHERE updated_at < NOW() - (max_age_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RAISE NOTICE 'Cleaned up % stale product catalog embeddings', deleted_count;
    RETURN deleted_count;
END;
$$;


-- ---------------------------------------------------------------------------
-- Step 7: Row-Level Security (optional, for multi-tenant scenarios)
-- ---------------------------------------------------------------------------

-- Enable RLS on embeddings tables
-- ALTER TABLE product_catalog_embeddings ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY tenant_isolation ON product_catalog_embeddings
--     USING (metadata->>'tenant_id' = current_setting('app.current_tenant'));


-- ---------------------------------------------------------------------------
-- Step 8: Verify Setup
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    ext_count INTEGER;
    table_count INTEGER;
    index_count INTEGER;
    func_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO ext_count
    FROM pg_extension WHERE extname IN ('vector', 'pg_trgm', 'uuid-ossp');

    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_name IN ('product_catalog_embeddings', 'document_embeddings')
    AND table_schema = 'public';

    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE tablename IN ('product_catalog_embeddings', 'document_embeddings')
    AND schemaname = 'public';

    SELECT COUNT(*) INTO func_count
    FROM information_schema.routines
    WHERE (routine_name LIKE 'search_product_catalog%' OR routine_name LIKE 'search_documents%')
    AND routine_schema = 'public';

    RAISE NOTICE '=== pgvector Setup Verification ===';
    RAISE NOTICE 'Extensions installed: %', ext_count;
    RAISE NOTICE 'Tables created: %', table_count;
    RAISE NOTICE 'Indexes created: %', index_count;
    RAISE NOTICE 'Functions created: %', func_count;
    RAISE NOTICE '===================================';
END $$;
