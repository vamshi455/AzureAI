"""
Product Catalog Indexing Pipeline for pgvector RAG.

Indexes product catalog documents (PDFs, markdown, structured data) into
PostgreSQL with pgvector for semantic retrieval. Uses Azure OpenAI embeddings
with a chunking strategy optimized for product documentation.

Usage:
    python index_product_catalog.py --source-dir /path/to/catalog --batch-size 100
    python index_product_catalog.py --source-type database --connection-string "..."
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Optional

import asyncpg
from openai import AsyncAzureOpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("product_catalog_indexer")


class ChunkStrategy(str, Enum):
    """Supported text chunking strategies."""
    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"
    RECURSIVE = "recursive"


@dataclass
class IndexingConfig:
    """Configuration for the indexing pipeline."""
    # PostgreSQL / pgvector
    pg_connection_string: str = os.getenv(
        "PGVECTOR_CONNECTION_STRING",
        "postgresql://user:password@localhost:5432/vectordb",
    )
    pg_table_name: str = "product_catalog_embeddings"
    pg_pool_min_size: int = 2
    pg_pool_max_size: int = 10

    # Azure OpenAI Embeddings
    aoai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    aoai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    aoai_api_version: str = "2025-04-01-preview"
    embedding_deployment: str = os.getenv(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large-rag"
    )
    embedding_dimensions: int = 1536

    # Chunking
    chunk_strategy: ChunkStrategy = ChunkStrategy.RECURSIVE
    chunk_size: int = 512          # tokens (approximate)
    chunk_overlap: int = 64        # tokens overlap between chunks
    min_chunk_size: int = 50       # minimum chunk size to keep

    # Batching
    embedding_batch_size: int = 100  # Max items per embedding API call
    db_batch_size: int = 200         # Max items per DB insert batch

    # Source
    source_directory: str = ""
    file_extensions: list[str] = field(
        default_factory=lambda: [".md", ".txt", ".json", ".csv"]
    )


@dataclass
class DocumentChunk:
    """A chunk of text from a source document, ready for embedding."""
    chunk_id: str
    document_id: str
    source_file: str
    content: str
    metadata: dict
    chunk_index: int
    total_chunks: int
    content_hash: str = ""
    embedding: Optional[list[float]] = None

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Text Chunking
# ---------------------------------------------------------------------------

class RecursiveTextChunker:
    """
    Recursively splits text using a hierarchy of separators, attempting to
    keep semantically meaningful units together. Inspired by LangChain's
    RecursiveCharacterTextSplitter but operates on approximate token counts.
    """

    # Characters per token approximation for English text
    CHARS_PER_TOKEN = 4

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        min_chunk_size: int = 50,
    ):
        self.chunk_size_chars = chunk_size * self.CHARS_PER_TOKEN
        self.chunk_overlap_chars = chunk_overlap * self.CHARS_PER_TOKEN
        self.min_chunk_chars = min_chunk_size * self.CHARS_PER_TOKEN
        self.separators = [
            "\n\n\n",   # Triple newline (section breaks)
            "\n\n",      # Paragraph breaks
            "\n",         # Line breaks
            ". ",         # Sentence boundaries
            ", ",         # Clause boundaries
            " ",          # Word boundaries
            "",           # Character level (last resort)
        ]

    def chunk_text(self, text: str) -> list[str]:
        """Split text into chunks using recursive separator strategy."""
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.chunk_size_chars:
            return [text]
        return self._recursive_split(text, self.separators)

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text, trying each separator in order."""
        if not text:
            return []

        final_chunks: list[str] = []
        separator = separators[-1]  # Default to last separator

        # Find the best separator that actually splits the text
        for sep in separators:
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                break

        # Split on the chosen separator
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        # Merge splits into chunks of appropriate size
        current_chunk_parts: list[str] = []
        current_length = 0

        for split_part in splits:
            part_length = len(split_part) + (len(separator) if current_chunk_parts else 0)

            if current_length + part_length > self.chunk_size_chars and current_chunk_parts:
                # Current chunk is full, finalize it
                chunk_text = separator.join(current_chunk_parts)
                if len(chunk_text) >= self.min_chunk_chars:
                    final_chunks.append(chunk_text)

                # Keep overlap
                overlap_parts: list[str] = []
                overlap_length = 0
                for part in reversed(current_chunk_parts):
                    if overlap_length + len(part) > self.chunk_overlap_chars:
                        break
                    overlap_parts.insert(0, part)
                    overlap_length += len(part)

                current_chunk_parts = overlap_parts
                current_length = overlap_length

            current_chunk_parts.append(split_part)
            current_length += part_length

        # Handle remaining text
        if current_chunk_parts:
            remaining = separator.join(current_chunk_parts)
            if len(remaining) >= self.min_chunk_chars:
                final_chunks.append(remaining)
            elif final_chunks:
                # Append to previous chunk if too small
                final_chunks[-1] = final_chunks[-1] + separator + remaining

        return final_chunks


# ---------------------------------------------------------------------------
# Document Parsing
# ---------------------------------------------------------------------------

class ProductCatalogParser:
    """Parse various document formats into text chunks with metadata."""

    def __init__(self, chunker: RecursiveTextChunker):
        self.chunker = chunker

    def parse_file(self, file_path: Path) -> list[DocumentChunk]:
        """Parse a file and return document chunks with metadata."""
        suffix = file_path.suffix.lower()
        document_id = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]

        if suffix in (".md", ".txt"):
            return self._parse_text_file(file_path, document_id)
        elif suffix == ".json":
            return self._parse_json_catalog(file_path, document_id)
        elif suffix == ".csv":
            return self._parse_csv_catalog(file_path, document_id)
        else:
            logger.warning(f"Unsupported file type: {suffix} for {file_path}")
            return []

    def _parse_text_file(self, file_path: Path, document_id: str) -> list[DocumentChunk]:
        """Parse markdown or plain text files."""
        content = file_path.read_text(encoding="utf-8")
        chunks_text = self.chunker.chunk_text(content)

        # Extract title from first heading if markdown
        title = file_path.stem
        heading_match = re.match(r"^#\s+(.+)", content)
        if heading_match:
            title = heading_match.group(1).strip()

        # Detect document type from filename pattern
        doc_type = "product_documentation"
        extra_metadata: dict = {}
        if file_path.name.startswith("equipment_"):
            doc_type = "equipment_health"
            eq_match = re.search(r"EQ-\d+-\w+-\d+", content)
            if eq_match:
                extra_metadata["equipment_id"] = eq_match.group(0)
            hs_match = re.search(r"Health Score\s*\|\s*(\d+)/100", content)
            if hs_match:
                extra_metadata["health_score"] = int(hs_match.group(1))
            risk_match = re.search(r"Failure Risk\s*\|\s*(\w+)", content)
            if risk_match:
                extra_metadata["failure_risk"] = risk_match.group(1)
        elif file_path.name.startswith("customer_"):
            doc_type = "customer_360"
            kunnr_match = re.search(r"SAP Customer \(KUNNR\)\s*\|\s*(\d+)", content)
            if kunnr_match:
                extra_metadata["customer_number"] = kunnr_match.group(1)

        chunks = []
        for i, chunk_text in enumerate(chunks_text):
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document_id}_chunk_{i:04d}",
                    document_id=document_id,
                    source_file=str(file_path),
                    content=chunk_text,
                    metadata={
                        "title": title,
                        "file_type": file_path.suffix,
                        "document_type": doc_type,
                        **extra_metadata,
                    },
                    chunk_index=i,
                    total_chunks=len(chunks_text),
                )
            )
        return chunks

    def _parse_json_catalog(self, file_path: Path, document_id: str) -> list[DocumentChunk]:
        """Parse structured JSON product catalog entries."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        products = data if isinstance(data, list) else data.get("products", [data])
        chunks = []

        for idx, product in enumerate(products):
            # Build a textual representation of the product
            text_parts = []
            material_number = product.get("material_number", product.get("sku", f"PROD_{idx}"))

            if "name" in product or "product_name" in product:
                text_parts.append(f"Product: {product.get('name', product.get('product_name'))}")
            if material_number:
                text_parts.append(f"Material Number: {material_number}")
            if "description" in product:
                text_parts.append(f"Description: {product['description']}")
            if "category" in product or "material_group" in product:
                text_parts.append(f"Category: {product.get('category', product.get('material_group'))}")
            if "specifications" in product:
                specs = product["specifications"]
                if isinstance(specs, dict):
                    spec_text = "; ".join(f"{k}: {v}" for k, v in specs.items())
                    text_parts.append(f"Specifications: {spec_text}")
                else:
                    text_parts.append(f"Specifications: {specs}")
            if "applications" in product:
                apps = product["applications"]
                if isinstance(apps, list):
                    text_parts.append(f"Applications: {', '.join(apps)}")

            content = "\n".join(text_parts)

            # For large products, chunk the content further
            sub_chunks = self.chunker.chunk_text(content)
            for i, chunk_text in enumerate(sub_chunks):
                prod_doc_id = f"{document_id}_{idx}"
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{prod_doc_id}_chunk_{i:04d}",
                        document_id=prod_doc_id,
                        source_file=str(file_path),
                        content=chunk_text,
                        metadata={
                            "material_number": material_number,
                            "product_name": product.get("name", product.get("product_name", "")),
                            "category": product.get("category", product.get("material_group", "")),
                            "file_type": ".json",
                            "document_type": "product_catalog",
                        },
                        chunk_index=i,
                        total_chunks=len(sub_chunks),
                    )
                )

        return chunks

    def _parse_csv_catalog(self, file_path: Path, document_id: str) -> list[DocumentChunk]:
        """Parse CSV product catalog files."""
        import csv

        chunks = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                # Build text from CSV columns
                text_parts = [f"{key}: {value}" for key, value in row.items() if value]
                content = "\n".join(text_parts)

                material_number = row.get(
                    "material_number", row.get("sku", row.get("product_id", f"ROW_{idx}"))
                )

                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{document_id}_{idx:06d}_chunk_0000",
                        document_id=f"{document_id}_{idx:06d}",
                        source_file=str(file_path),
                        content=content,
                        metadata={
                            "material_number": material_number,
                            "product_name": row.get("name", row.get("product_name", "")),
                            "category": row.get("category", row.get("material_group", "")),
                            "file_type": ".csv",
                            "document_type": "product_catalog",
                        },
                        chunk_index=0,
                        total_chunks=1,
                    )
                )

        return chunks


# ---------------------------------------------------------------------------
# Embedding Generation
# ---------------------------------------------------------------------------

class EmbeddingGenerator:
    """Generate embeddings using Azure OpenAI's text-embedding-3-large model."""

    def __init__(self, config: IndexingConfig):
        self.client = AsyncAzureOpenAI(
            azure_endpoint=config.aoai_endpoint,
            api_key=config.aoai_api_key,
            api_version=config.aoai_api_version,
        )
        self.deployment = config.embedding_deployment
        self.dimensions = config.embedding_dimensions
        self.batch_size = config.embedding_batch_size

    async def generate_embeddings(
        self, chunks: list[DocumentChunk]
    ) -> list[DocumentChunk]:
        """Generate embeddings for a list of document chunks in batches."""
        total_batches = (len(chunks) + self.batch_size - 1) // self.batch_size
        logger.info(
            f"Generating embeddings for {len(chunks)} chunks in {total_batches} batches..."
        )

        for batch_idx in range(0, len(chunks), self.batch_size):
            batch = chunks[batch_idx : batch_idx + self.batch_size]
            texts = [chunk.content for chunk in batch]

            try:
                response = await self.client.embeddings.create(
                    input=texts,
                    model=self.deployment,
                    dimensions=self.dimensions,
                )

                for chunk, embedding_data in zip(batch, response.data):
                    chunk.embedding = embedding_data.embedding

                batch_num = batch_idx // self.batch_size + 1
                logger.info(
                    f"  Batch {batch_num}/{total_batches}: "
                    f"embedded {len(batch)} chunks "
                    f"({response.usage.total_tokens} tokens)"
                )

            except Exception as e:
                logger.error(f"Embedding generation failed for batch starting at {batch_idx}: {e}")
                # Retry individual items in the failed batch
                for chunk in batch:
                    try:
                        single_response = await self.client.embeddings.create(
                            input=[chunk.content],
                            model=self.deployment,
                            dimensions=self.dimensions,
                        )
                        chunk.embedding = single_response.data[0].embedding
                    except Exception as retry_err:
                        logger.error(
                            f"Failed to embed chunk {chunk.chunk_id}: {retry_err}"
                        )
                        # Leave embedding as None; will be skipped during storage

            # Rate limiting: brief pause between batches
            if batch_idx + self.batch_size < len(chunks):
                await asyncio.sleep(0.1)

        embedded_count = sum(1 for c in chunks if c.embedding is not None)
        logger.info(f"Successfully embedded {embedded_count}/{len(chunks)} chunks.")
        return chunks


# ---------------------------------------------------------------------------
# pgvector Storage
# ---------------------------------------------------------------------------

class PgVectorStore:
    """Manages storage and retrieval of embeddings in PostgreSQL with pgvector."""

    def __init__(self, config: IndexingConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self) -> None:
        """Create connection pool and ensure table exists."""
        self.pool = await asyncpg.create_pool(
            self.config.pg_connection_string,
            min_size=self.config.pg_pool_min_size,
            max_size=self.config.pg_pool_max_size,
        )

        async with self.pool.acquire() as conn:
            # Ensure pgvector extension is available
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Create embeddings table if not exists
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.pg_table_name} (
                    id              TEXT PRIMARY KEY,
                    document_id     TEXT NOT NULL,
                    source_file     TEXT,
                    content         TEXT NOT NULL,
                    content_hash    TEXT NOT NULL,
                    metadata        JSONB DEFAULT '{{}}'::jsonb,
                    chunk_index     INTEGER,
                    total_chunks    INTEGER,
                    embedding       vector({self.config.embedding_dimensions}),
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # Create indexes
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.config.pg_table_name}_doc_id
                ON {self.config.pg_table_name} (document_id);
            """)
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.config.pg_table_name}_content_hash
                ON {self.config.pg_table_name} (content_hash);
            """)
            # HNSW index for approximate nearest neighbor search
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.config.pg_table_name}_embedding_hnsw
                ON {self.config.pg_table_name}
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 200);
            """)
            # GIN index on metadata for filtered queries
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.config.pg_table_name}_metadata_gin
                ON {self.config.pg_table_name}
                USING gin (metadata jsonb_path_ops);
            """)

        logger.info("pgvector store initialized successfully.")

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> int:
        """Upsert document chunks into pgvector. Returns count of rows written."""
        if not self.pool:
            raise RuntimeError("Store not initialized. Call initialize() first.")

        # Filter out chunks without embeddings
        valid_chunks = [c for c in chunks if c.embedding is not None]
        if not valid_chunks:
            logger.warning("No valid chunks with embeddings to store.")
            return 0

        inserted = 0
        batch_size = self.config.db_batch_size

        async with self.pool.acquire() as conn:
            for batch_start in range(0, len(valid_chunks), batch_size):
                batch = valid_chunks[batch_start : batch_start + batch_size]

                # Check which chunks already exist with same content_hash (skip if unchanged)
                chunk_ids = [c.chunk_id for c in batch]
                content_hashes = [c.content_hash for c in batch]

                existing = await conn.fetch(
                    f"""
                    SELECT id, content_hash
                    FROM {self.config.pg_table_name}
                    WHERE id = ANY($1::text[])
                    """,
                    chunk_ids,
                )
                existing_map = {row["id"]: row["content_hash"] for row in existing}

                # Filter to only new or changed chunks
                chunks_to_write = []
                for chunk in batch:
                    existing_hash = existing_map.get(chunk.chunk_id)
                    if existing_hash != chunk.content_hash:
                        chunks_to_write.append(chunk)

                if not chunks_to_write:
                    continue

                # Batch upsert using unnest for performance
                values = [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.source_file,
                        chunk.content,
                        chunk.content_hash,
                        json.dumps(chunk.metadata),
                        chunk.chunk_index,
                        chunk.total_chunks,
                        json.dumps(chunk.embedding),
                    )
                    for chunk in chunks_to_write
                ]

                await conn.executemany(
                    f"""
                    INSERT INTO {self.config.pg_table_name}
                        (id, document_id, source_file, content, content_hash,
                         metadata, chunk_index, total_chunks, embedding, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9::vector, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        content_hash = EXCLUDED.content_hash,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                    """,
                    values,
                )

                inserted += len(chunks_to_write)
                logger.info(
                    f"  Upserted {len(chunks_to_write)} chunks "
                    f"(skipped {len(batch) - len(chunks_to_write)} unchanged)"
                )

        return inserted

    async def delete_by_document(self, document_id: str) -> int:
        """Delete all chunks for a given document ID."""
        if not self.pool:
            raise RuntimeError("Store not initialized.")

        async with self.pool.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {self.config.pg_table_name} WHERE document_id = $1",
                document_id,
            )
            count = int(result.split()[-1])
            logger.info(f"Deleted {count} chunks for document {document_id}.")
            return count

    async def get_stats(self) -> dict:
        """Get index statistics."""
        if not self.pool:
            raise RuntimeError("Store not initialized.")

        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM {self.config.pg_table_name}"
            )
            documents = await conn.fetchval(
                f"SELECT COUNT(DISTINCT document_id) FROM {self.config.pg_table_name}"
            )
            return {
                "total_chunks": total,
                "total_documents": documents,
                "table_name": self.config.pg_table_name,
                "embedding_dimensions": self.config.embedding_dimensions,
            }

    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("pgvector connection pool closed.")


# ---------------------------------------------------------------------------
# Main Indexing Pipeline
# ---------------------------------------------------------------------------

async def run_indexing_pipeline(config: IndexingConfig) -> dict:
    """
    Execute the full indexing pipeline:
    1. Scan source directory for documents
    2. Parse and chunk documents
    3. Generate embeddings via Azure OpenAI
    4. Store in pgvector

    Returns a summary of the indexing run.
    """
    start_time = time.time()

    # Initialize components
    chunker = RecursiveTextChunker(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        min_chunk_size=config.min_chunk_size,
    )
    parser = ProductCatalogParser(chunker)
    embedder = EmbeddingGenerator(config)
    store = PgVectorStore(config)

    try:
        await store.initialize()

        # Step 1: Discover and parse documents
        source_dir = Path(config.source_directory)
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {source_dir}")

        all_chunks: list[DocumentChunk] = []
        files_processed = 0

        for ext in config.file_extensions:
            for file_path in source_dir.rglob(f"*{ext}"):
                try:
                    file_chunks = parser.parse_file(file_path)
                    all_chunks.extend(file_chunks)
                    files_processed += 1
                    logger.info(
                        f"Parsed {file_path.name}: {len(file_chunks)} chunks"
                    )
                except Exception as e:
                    logger.error(f"Failed to parse {file_path}: {e}")

        logger.info(
            f"Total: {files_processed} files, {len(all_chunks)} chunks"
        )

        if not all_chunks:
            logger.warning("No chunks to index. Exiting.")
            return {
                "status": "completed",
                "files_processed": 0,
                "chunks_created": 0,
                "chunks_stored": 0,
                "duration_seconds": time.time() - start_time,
            }

        # Step 2: Generate embeddings
        all_chunks = await embedder.generate_embeddings(all_chunks)

        # Step 3: Store in pgvector
        stored_count = await store.upsert_chunks(all_chunks)

        # Get final stats
        stats = await store.get_stats()

        duration = time.time() - start_time
        summary = {
            "status": "completed",
            "files_processed": files_processed,
            "chunks_created": len(all_chunks),
            "chunks_stored": stored_count,
            "total_chunks_in_index": stats["total_chunks"],
            "total_documents_in_index": stats["total_documents"],
            "duration_seconds": round(duration, 2),
            "throughput_chunks_per_second": round(len(all_chunks) / duration, 1),
        }

        logger.info(f"Indexing complete: {json.dumps(summary, indent=2)}")
        return summary

    finally:
        await store.close()


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Index product catalog documents into pgvector for RAG retrieval."
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        required=True,
        help="Path to directory containing product catalog documents.",
    )
    parser.add_argument(
        "--pg-connection",
        type=str,
        default=os.getenv("PGVECTOR_CONNECTION_STRING"),
        help="PostgreSQL connection string.",
    )
    parser.add_argument(
        "--table-name",
        type=str,
        default="product_catalog_embeddings",
        help="Target table name in PostgreSQL.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Target chunk size in tokens (default: 512).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=64,
        help="Chunk overlap in tokens (default: 64).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Embedding batch size (default: 100).",
    )
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=1536,
        help="Embedding vector dimensions (default: 1536).",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    config = IndexingConfig(
        source_directory=args.source_dir,
        pg_table_name=args.table_name,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        embedding_batch_size=args.batch_size,
        embedding_dimensions=args.embedding_dimensions,
    )

    if args.pg_connection:
        config.pg_connection_string = args.pg_connection

    asyncio.run(run_indexing_pipeline(config))


if __name__ == "__main__":
    main()
