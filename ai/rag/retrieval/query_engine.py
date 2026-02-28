"""
RAG Query Engine with Hybrid Search (Semantic + Keyword).

Searches pgvector for relevant context using both dense vector similarity
and sparse keyword matching, then generates grounded answers using Azure OpenAI.

Usage:
    from ai.rag.retrieval.query_engine import RAGQueryEngine, QueryConfig
    engine = RAGQueryEngine(config)
    await engine.initialize()
    result = await engine.query("What products are suitable for high-temperature environments?")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Optional

import asyncpg
from openai import AsyncAzureOpenAI

logger = logging.getLogger("rag_query_engine")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class SearchMode(str, Enum):
    """Search strategies for retrieval."""
    SEMANTIC = "semantic"         # Dense vector similarity only
    KEYWORD = "keyword"           # PostgreSQL full-text search only
    HYBRID = "hybrid"             # Combined semantic + keyword with RRF


@dataclass
class QueryConfig:
    """Configuration for the RAG query engine."""
    # PostgreSQL / pgvector
    pg_connection_string: str = os.getenv(
        "PGVECTOR_CONNECTION_STRING",
        "postgresql://user:password@localhost:5432/vectordb",
    )
    pg_table_name: str = "product_catalog_embeddings"
    pg_pool_min_size: int = 2
    pg_pool_max_size: int = 10

    # Azure OpenAI
    aoai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    aoai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    aoai_api_version: str = "2025-04-01-preview"
    embedding_deployment: str = os.getenv(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large-rag"
    )
    chat_deployment: str = os.getenv(
        "AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-sales-insights"
    )
    embedding_dimensions: int = 1536

    # Search settings
    search_mode: SearchMode = SearchMode.HYBRID
    top_k: int = 5                        # Number of results to return
    semantic_weight: float = 0.7          # Weight for semantic score in hybrid
    keyword_weight: float = 0.3           # Weight for keyword score in hybrid
    rrf_k: int = 60                       # Reciprocal Rank Fusion constant
    similarity_threshold: float = 0.3     # Minimum similarity score to include
    rerank_enabled: bool = True           # Re-rank results by combined score

    # Generation settings
    chat_temperature: float = 0.1
    chat_max_tokens: int = 2048
    include_citations: bool = True
    max_context_tokens: int = 8000        # Max tokens for context window


@dataclass
class SearchResult:
    """A single search result with scoring details."""
    chunk_id: str
    document_id: str
    content: str
    metadata: dict
    source_file: str
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    combined_score: float = 0.0
    chunk_index: int = 0
    total_chunks: int = 1


@dataclass
class QueryResult:
    """Complete result of a RAG query including answer and sources."""
    query: str
    answer: str
    sources: list[SearchResult]
    search_mode: str
    total_results_found: int
    latency_ms: float
    model_used: str
    token_usage: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Query Engine
# ---------------------------------------------------------------------------

class RAGQueryEngine:
    """
    RAG query engine that combines pgvector semantic search with PostgreSQL
    full-text search for hybrid retrieval, then generates grounded answers
    using Azure OpenAI.
    """

    def __init__(self, config: Optional[QueryConfig] = None):
        self.config = config or QueryConfig()
        self.pool: Optional[asyncpg.Pool] = None
        self.openai_client: Optional[AsyncAzureOpenAI] = None

    async def initialize(self) -> None:
        """Initialize database pool and OpenAI client."""
        self.pool = await asyncpg.create_pool(
            self.config.pg_connection_string,
            min_size=self.config.pg_pool_min_size,
            max_size=self.config.pg_pool_max_size,
        )

        self.openai_client = AsyncAzureOpenAI(
            azure_endpoint=self.config.aoai_endpoint,
            api_key=self.config.aoai_api_key,
            api_version=self.config.aoai_api_version,
        )

        # Ensure full-text search index exists
        async with self.pool.acquire() as conn:
            # Create tsvector column and index for keyword search
            try:
                await conn.execute(f"""
                    ALTER TABLE {self.config.pg_table_name}
                    ADD COLUMN IF NOT EXISTS content_tsv tsvector
                    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
                """)
            except Exception:
                # Column might already exist or table uses different approach
                logger.debug("tsvector column may already exist, proceeding.")

            try:
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.config.pg_table_name}_fts
                    ON {self.config.pg_table_name}
                    USING gin (content_tsv);
                """)
            except Exception:
                logger.debug("FTS index may already exist, proceeding.")

        logger.info("RAG Query Engine initialized.")

    async def query(
        self,
        question: str,
        metadata_filter: Optional[dict] = None,
        top_k: Optional[int] = None,
        search_mode: Optional[SearchMode] = None,
    ) -> QueryResult:
        """
        Execute a RAG query: retrieve relevant context and generate an answer.

        Args:
            question: The user's natural language question.
            metadata_filter: Optional JSONB filter for metadata (e.g., {"category": "Electronics"}).
            top_k: Override the number of results to retrieve.
            search_mode: Override the search mode.

        Returns:
            QueryResult with the generated answer and source documents.
        """
        start_time = time.time()
        effective_top_k = top_k or self.config.top_k
        effective_mode = search_mode or self.config.search_mode

        # Step 1: Retrieve relevant context
        search_results = await self._search(
            question, effective_mode, effective_top_k, metadata_filter
        )

        # Step 2: Build context from search results
        context = self._build_context(search_results)

        # Step 3: Generate answer using Azure OpenAI
        answer, token_usage = await self._generate_answer(question, context, search_results)

        latency_ms = (time.time() - start_time) * 1000

        return QueryResult(
            query=question,
            answer=answer,
            sources=search_results,
            search_mode=effective_mode.value,
            total_results_found=len(search_results),
            latency_ms=round(latency_ms, 1),
            model_used=self.config.chat_deployment,
            token_usage=token_usage,
        )

    async def search_only(
        self,
        question: str,
        metadata_filter: Optional[dict] = None,
        top_k: Optional[int] = None,
        search_mode: Optional[SearchMode] = None,
    ) -> list[SearchResult]:
        """Execute search without generation. Useful for debugging retrieval."""
        effective_top_k = top_k or self.config.top_k
        effective_mode = search_mode or self.config.search_mode
        return await self._search(question, effective_mode, effective_top_k, metadata_filter)

    # -- Internal Search Methods --

    async def _search(
        self,
        query: str,
        mode: SearchMode,
        top_k: int,
        metadata_filter: Optional[dict],
    ) -> list[SearchResult]:
        """Dispatch to the appropriate search strategy."""
        if mode == SearchMode.SEMANTIC:
            return await self._semantic_search(query, top_k, metadata_filter)
        elif mode == SearchMode.KEYWORD:
            return await self._keyword_search(query, top_k, metadata_filter)
        elif mode == SearchMode.HYBRID:
            return await self._hybrid_search(query, top_k, metadata_filter)
        else:
            raise ValueError(f"Unknown search mode: {mode}")

    async def _get_query_embedding(self, query: str) -> list[float]:
        """Generate embedding for the search query."""
        response = await self.openai_client.embeddings.create(
            input=[query],
            model=self.config.embedding_deployment,
            dimensions=self.config.embedding_dimensions,
        )
        return response.data[0].embedding

    async def _semantic_search(
        self,
        query: str,
        top_k: int,
        metadata_filter: Optional[dict],
    ) -> list[SearchResult]:
        """Dense vector similarity search using pgvector."""
        query_embedding = await self._get_query_embedding(query)

        filter_clause = ""
        filter_params: list = [json.dumps(query_embedding), top_k]

        if metadata_filter:
            conditions = []
            for i, (key, value) in enumerate(metadata_filter.items(), start=3):
                conditions.append(f"metadata->>'{key}' = ${i}")
                filter_params.append(str(value))
            filter_clause = "WHERE " + " AND ".join(conditions)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    id, document_id, content, metadata, source_file,
                    chunk_index, total_chunks,
                    1 - (embedding <=> $1::vector) AS similarity_score
                FROM {self.config.pg_table_name}
                {filter_clause}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                *filter_params,
            )

        results = []
        for row in rows:
            score = float(row["similarity_score"])
            if score >= self.config.similarity_threshold:
                results.append(
                    SearchResult(
                        chunk_id=row["id"],
                        document_id=row["document_id"],
                        content=row["content"],
                        metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else dict(row["metadata"]),
                        source_file=row["source_file"],
                        semantic_score=score,
                        combined_score=score,
                        chunk_index=row["chunk_index"],
                        total_chunks=row["total_chunks"],
                    )
                )

        return results

    async def _keyword_search(
        self,
        query: str,
        top_k: int,
        metadata_filter: Optional[dict],
    ) -> list[SearchResult]:
        """Full-text keyword search using PostgreSQL tsvector."""
        # Convert natural language query to tsquery
        # Clean the query for tsquery compatibility
        clean_query = re.sub(r"[^\w\s]", " ", query)
        tsquery_terms = " & ".join(clean_query.split())

        filter_clause = ""
        filter_params: list = [tsquery_terms, top_k]

        if metadata_filter:
            conditions = []
            for i, (key, value) in enumerate(metadata_filter.items(), start=3):
                conditions.append(f"metadata->>'{key}' = ${i}")
                filter_params.append(str(value))
            filter_clause = "AND " + " AND ".join(conditions)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    id, document_id, content, metadata, source_file,
                    chunk_index, total_chunks,
                    ts_rank_cd(content_tsv, to_tsquery('english', $1)) AS rank_score
                FROM {self.config.pg_table_name}
                WHERE content_tsv @@ to_tsquery('english', $1)
                {filter_clause}
                ORDER BY rank_score DESC
                LIMIT $2
                """,
                *filter_params,
            )

        results = []
        for row in rows:
            score = float(row["rank_score"])
            results.append(
                SearchResult(
                    chunk_id=row["id"],
                    document_id=row["document_id"],
                    content=row["content"],
                    metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else dict(row["metadata"]),
                    source_file=row["source_file"],
                    keyword_score=score,
                    combined_score=score,
                    chunk_index=row["chunk_index"],
                    total_chunks=row["total_chunks"],
                )
            )

        return results

    async def _hybrid_search(
        self,
        query: str,
        top_k: int,
        metadata_filter: Optional[dict],
    ) -> list[SearchResult]:
        """
        Hybrid search combining semantic and keyword results using
        Reciprocal Rank Fusion (RRF).

        RRF Score = sum(1 / (k + rank_i)) for each result list
        """
        # Execute both searches in parallel
        semantic_task = self._semantic_search(query, top_k * 2, metadata_filter)
        keyword_task = self._keyword_search(query, top_k * 2, metadata_filter)

        semantic_results, keyword_results = await asyncio.gather(
            semantic_task, keyword_task
        )

        # Build RRF scores
        rrf_scores: dict[str, float] = {}
        result_map: dict[str, SearchResult] = {}

        k = self.config.rrf_k

        # Score semantic results
        for rank, result in enumerate(semantic_results):
            rrf_score = self.config.semantic_weight / (k + rank + 1)
            rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0) + rrf_score
            if result.chunk_id not in result_map:
                result_map[result.chunk_id] = result

        # Score keyword results
        for rank, result in enumerate(keyword_results):
            rrf_score = self.config.keyword_weight / (k + rank + 1)
            rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0) + rrf_score
            if result.chunk_id not in result_map:
                result_map[result.chunk_id] = result
            else:
                # Update keyword score on existing result
                result_map[result.chunk_id].keyword_score = result.keyword_score

        # Sort by combined RRF score and take top_k
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        results = []
        for chunk_id in sorted_ids[:top_k]:
            result = result_map[chunk_id]
            result.combined_score = rrf_scores[chunk_id]
            results.append(result)

        logger.info(
            f"Hybrid search: {len(semantic_results)} semantic + "
            f"{len(keyword_results)} keyword -> {len(results)} merged results"
        )

        return results

    # -- Context Building --

    def _build_context(self, results: list[SearchResult]) -> str:
        """Build a context string from search results for the LLM prompt."""
        if not results:
            return "No relevant documents were found."

        context_parts = []
        for i, result in enumerate(results, 1):
            source_info = result.metadata.get("product_name") or result.metadata.get("title", "Unknown")
            material = result.metadata.get("material_number", "")
            source_label = f"{source_info}"
            if material:
                source_label += f" (Material: {material})"

            context_parts.append(
                f"[Source {i}: {source_label}]\n{result.content}\n"
            )

        return "\n---\n".join(context_parts)

    # -- Answer Generation --

    async def _generate_answer(
        self,
        question: str,
        context: str,
        sources: list[SearchResult],
    ) -> tuple[str, dict]:
        """Generate a grounded answer using Azure OpenAI with retrieved context."""
        system_prompt = (
            "You are a knowledgeable product specialist for a manufacturing company. "
            "Answer the user's question using ONLY the information provided in the context below. "
            "If the context does not contain enough information to fully answer the question, "
            "clearly state what you can answer and what information is missing.\n\n"
            "RULES:\n"
            "1. Ground every claim in the provided context.\n"
            "2. Cite sources using [Source N] notation.\n"
            "3. If multiple sources agree, synthesize them into a coherent answer.\n"
            "4. If sources conflict, present both perspectives with their citations.\n"
            "5. Do not make up information not present in the context.\n"
            "6. Use clear, professional language suitable for a business audience.\n"
        )

        user_message = (
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Provide a detailed answer grounded in the context above, citing sources."
        )

        response = await self.openai_client.chat.completions.create(
            model=self.config.chat_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=self.config.chat_temperature,
            max_tokens=self.config.chat_max_tokens,
        )

        answer = response.choices[0].message.content or ""
        token_usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        return answer, token_usage

    # -- Streaming Support --

    async def query_stream(
        self,
        question: str,
        metadata_filter: Optional[dict] = None,
        top_k: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream the RAG answer token by token. Useful for real-time UI rendering.
        Yields answer chunks as they arrive from the model.
        """
        effective_top_k = top_k or self.config.top_k

        # Retrieve context
        search_results = await self._search(
            question, self.config.search_mode, effective_top_k, metadata_filter
        )
        context = self._build_context(search_results)

        system_prompt = (
            "You are a knowledgeable product specialist for a manufacturing company. "
            "Answer using ONLY the provided context. Cite sources using [Source N]."
        )

        user_message = (
            f"Context:\n{context}\n\nQuestion: {question}\n\n"
            "Provide a detailed, grounded answer."
        )

        stream = await self.openai_client.chat.completions.create(
            model=self.config.chat_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=self.config.chat_temperature,
            max_tokens=self.config.chat_max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # -- Lifecycle --

    async def close(self) -> None:
        """Clean up resources."""
        if self.pool:
            await self.pool.close()
        logger.info("RAG Query Engine closed.")


# ---------------------------------------------------------------------------
# Convenience function for quick queries
# ---------------------------------------------------------------------------

async def quick_query(
    question: str,
    pg_connection: Optional[str] = None,
    metadata_filter: Optional[dict] = None,
) -> QueryResult:
    """
    One-shot convenience function for running a single RAG query.

    Args:
        question: The question to answer.
        pg_connection: Optional PostgreSQL connection string override.
        metadata_filter: Optional metadata filter.

    Returns:
        QueryResult with answer and sources.
    """
    config = QueryConfig()
    if pg_connection:
        config.pg_connection_string = pg_connection

    engine = RAGQueryEngine(config)
    try:
        await engine.initialize()
        return await engine.query(question, metadata_filter=metadata_filter)
    finally:
        await engine.close()


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAG Query Engine CLI")
    parser.add_argument("question", type=str, help="Question to answer")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["semantic", "keyword", "hybrid"],
        default="hybrid",
        help="Search mode (default: hybrid)",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of results")
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="Only search, don't generate answer",
    )
    args = parser.parse_args()

    async def main() -> None:
        config = QueryConfig(search_mode=SearchMode(args.mode))
        engine = RAGQueryEngine(config)
        await engine.initialize()

        try:
            if args.search_only:
                results = await engine.search_only(
                    args.question,
                    top_k=args.top_k,
                    search_mode=SearchMode(args.mode),
                )
                print(f"\n=== Search Results ({len(results)}) ===")
                for i, r in enumerate(results, 1):
                    print(f"\n--- Result {i} (score: {r.combined_score:.4f}) ---")
                    print(f"Source: {r.source_file}")
                    print(f"Metadata: {r.metadata}")
                    print(f"Content: {r.content[:300]}...")
            else:
                result = await engine.query(
                    args.question,
                    top_k=args.top_k,
                    search_mode=SearchMode(args.mode),
                )
                print(f"\n=== Answer (latency: {result.latency_ms:.0f}ms) ===")
                print(result.answer)
                print(f"\n=== Sources ({len(result.sources)}) ===")
                for i, s in enumerate(result.sources, 1):
                    print(f"  [{i}] {s.metadata.get('product_name', s.source_file)} "
                          f"(score: {s.combined_score:.4f})")
                print(f"\nTokens: {result.token_usage}")
        finally:
            await engine.close()

    asyncio.run(main())
