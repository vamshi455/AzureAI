"""
Index Equipment Health Documents into pgvector.
Reads Markdown files from rag-documents/equipment-health/, chunks them,
generates embeddings via Azure OpenAI, and stores in document_embeddings table.

Usage:
    python index_equipment_docs.py
    python index_equipment_docs.py --pg-host dp-psql-dev.postgres.database.azure.com
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

import asyncpg
from openai import AsyncAzureOpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("index_equipment_docs")

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = REPO_ROOT / "data-platform" / "synthetic-data" / "output" / "rag-documents" / "equipment-health"

# Chunking settings
CHUNK_SIZE = 512  # approximate tokens
CHUNK_OVERLAP = 64
CHARS_PER_TOKEN = 4  # rough approximation

# Embedding settings
EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large-rag")
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_BATCH_SIZE = 50
DB_BATCH_SIZE = 100


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks by approximate token count."""
    char_chunk = chunk_size * CHARS_PER_TOKEN
    char_overlap = overlap * CHARS_PER_TOKEN
    min_chunk_chars = 100

    chunks = []
    start = 0
    while start < len(text):
        end = start + char_chunk
        # Try to break at paragraph or sentence boundary
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", " "]:
                boundary = text.rfind(sep, start + char_chunk // 2, end + 100)
                if boundary > start:
                    end = boundary + len(sep)
                    break
        chunk = text[start:end].strip()
        if len(chunk) >= min_chunk_chars:
            chunks.append(chunk)
        start = end - char_overlap if end < len(text) else len(text)

    return chunks


def parse_equipment_metadata(filepath: Path, content: str) -> dict:
    """Extract metadata from equipment health Markdown file."""
    metadata = {"source_file": str(filepath.name)}

    # Extract equipment ID from filename (e.g., equipment_EQ-1100-A-006.md)
    match = re.search(r"equipment_(EQ-\d+-[A-Z]-\d+)", filepath.stem)
    if match:
        metadata["equipment_id"] = match.group(1)

    # Extract from content headers
    for pattern, key in [
        (r"\*\*Equipment ID\*\*:\s*`?([^`\n]+)`?", "equipment_id"),
        (r"\*\*Plant\*\*:\s*(\d+)", "plant_code"),
        (r"\*\*Health Score\*\*:\s*([\d.]+)", "health_score"),
        (r"\*\*Failure Risk\*\*:\s*\*?\*?(\w+)\*?\*?", "failure_risk"),
        (r"\*\*Production Line\*\*:\s*(\S+)", "production_line"),
    ]:
        m = re.search(pattern, content)
        if m:
            metadata[key] = m.group(1)

    return metadata


async def generate_embeddings(client: AsyncAzureOpenAI, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    response = await client.embeddings.create(
        input=texts,
        model=EMBEDDING_DEPLOYMENT,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return [item.embedding for item in response.data]


async def index_documents(args):
    """Main indexing pipeline."""
    if not DOCS_DIR.exists():
        logger.error(f"Documents directory not found: {DOCS_DIR}")
        return

    md_files = sorted(DOCS_DIR.glob("*.md"))
    logger.info(f"Found {len(md_files)} equipment health documents in {DOCS_DIR}")

    if not md_files:
        return

    # Connect to PostgreSQL
    pool = await asyncpg.create_pool(
        host=args.pg_host or os.getenv("PGHOST", "localhost"),
        port=args.pg_port or int(os.getenv("PGPORT", "5432")),
        database=args.pg_dbname or os.getenv("PGDATABASE", "postgres"),
        user=args.pg_user or os.getenv("PGUSER", "postgres"),
        password=args.pg_password or os.getenv("PGPASSWORD", ""),
        ssl="require" if (args.pg_sslmode or os.getenv("PGSSLMODE", "require")) == "require" else None,
        min_size=2,
        max_size=10,
    )

    # Initialize Azure OpenAI client
    aoai_client = AsyncAzureOpenAI(
        azure_endpoint=args.aoai_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        api_key=args.aoai_api_key or os.getenv("AZURE_OPENAI_API_KEY", ""),
        api_version="2025-04-01-preview",
    )

    # Clean existing equipment health embeddings
    async with pool.acquire() as conn:
        deleted = await conn.execute(
            "DELETE FROM document_embeddings WHERE document_type = 'equipment_health'"
        )
        logger.info(f"Cleared existing equipment_health embeddings: {deleted}")

    # Process all documents
    all_chunks = []
    for filepath in md_files:
        content = filepath.read_text(encoding="utf-8")
        metadata = parse_equipment_metadata(filepath, content)
        doc_id = metadata.get("equipment_id", filepath.stem)

        chunks = chunk_text(content)
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{doc_id}:{i}".encode()).hexdigest()
            content_hash = hashlib.md5(chunk.encode()).hexdigest()
            all_chunks.append({
                "id": chunk_id,
                "document_id": doc_id,
                "source_file": str(filepath.name),
                "content": chunk,
                "content_hash": content_hash,
                "metadata": json.dumps(metadata),
                "chunk_index": i,
                "total_chunks": len(chunks),
            })

    logger.info(f"Created {len(all_chunks)} chunks from {len(md_files)} documents.")

    # Generate embeddings in batches
    logger.info("Generating embeddings...")
    for i in range(0, len(all_chunks), EMBEDDING_BATCH_SIZE):
        batch = all_chunks[i : i + EMBEDDING_BATCH_SIZE]
        texts = [c["content"] for c in batch]

        try:
            embeddings = await generate_embeddings(aoai_client, texts)
            for chunk, emb in zip(batch, embeddings):
                chunk["embedding"] = emb
        except Exception as e:
            logger.error(f"Embedding batch {i // EMBEDDING_BATCH_SIZE + 1} failed: {e}")
            raise

        batch_num = i // EMBEDDING_BATCH_SIZE + 1
        total_batches = (len(all_chunks) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE
        logger.info(f"  Embedded batch {batch_num}/{total_batches}")

    # Insert into PostgreSQL in batches
    logger.info("Inserting into document_embeddings...")
    async with pool.acquire() as conn:
        for i in range(0, len(all_chunks), DB_BATCH_SIZE):
            batch = all_chunks[i : i + DB_BATCH_SIZE]
            await conn.executemany(
                """
                INSERT INTO document_embeddings
                    (id, document_id, source_file, content, content_hash,
                     document_type, metadata, chunk_index, total_chunks, embedding)
                VALUES ($1, $2, $3, $4, $5, 'equipment_health', $6::jsonb, $7, $8, $9::vector)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW()
                """,
                [
                    (
                        c["id"], c["document_id"], c["source_file"],
                        c["content"], c["content_hash"], c["metadata"],
                        c["chunk_index"], c["total_chunks"],
                        json.dumps(c["embedding"]),
                    )
                    for c in batch
                ],
            )
            logger.info(f"  Inserted DB batch {i // DB_BATCH_SIZE + 1}")

    # Verify
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM document_embeddings WHERE document_type = 'equipment_health'"
        )
        doc_count = await conn.fetchval(
            "SELECT count(DISTINCT document_id) FROM document_embeddings WHERE document_type = 'equipment_health'"
        )
    logger.info(f"Indexed {count} chunks from {doc_count} equipment health documents.")

    await pool.close()
    await aoai_client.close()
    logger.info("=== Indexing complete ===")


def main():
    parser = argparse.ArgumentParser(description="Index equipment health docs into pgvector")
    parser.add_argument("--pg-host", default=None)
    parser.add_argument("--pg-port", type=int, default=None)
    parser.add_argument("--pg-dbname", default=None)
    parser.add_argument("--pg-user", default=None)
    parser.add_argument("--pg-password", default=None)
    parser.add_argument("--pg-sslmode", default=None)
    parser.add_argument("--aoai-endpoint", default=None)
    parser.add_argument("--aoai-api-key", default=None)
    args = parser.parse_args()

    asyncio.run(index_documents(args))


if __name__ == "__main__":
    main()
