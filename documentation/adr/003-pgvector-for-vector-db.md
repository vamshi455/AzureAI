# ADR-003: PostgreSQL + pgvector for Vector Database

## Status

**Accepted** -- 2026-02-28

## Context

Our AI architecture requires a vector database to support Retrieval-Augmented Generation
(RAG). The RAG pipeline embeds documents and data from the Gold layer into vector
representations, stores them, and retrieves relevant context when users query the AI
system.

### Requirements

1. **Vector similarity search** -- Efficient cosine similarity, inner product, and L2
   distance searches across hundreds of thousands to low millions of embeddings.
2. **Metadata filtering** -- Ability to filter vector search results by metadata fields
   (e.g., document type, date range, department).
3. **Relational data co-location** -- Application data (users, sessions, prompt templates,
   audit logs) needs a relational store. Co-locating with vectors avoids managing a
   separate database.
4. **Azure managed service** -- Must be available as a managed Azure service to minimize
   operational overhead.
5. **Cost efficiency** -- Budget-appropriate for a small team; no multi-million-row scale
   at launch.
6. **Transactional consistency** -- ACID transactions for application data operations.

### Options Evaluated

| Option | Type | Azure Managed | Relational + Vector |
|--------|------|---------------|-------------------|
| PostgreSQL + pgvector | Relational + Vector extension | Yes (Flexible Server) | Yes |
| Azure AI Search | Dedicated search/vector service | Yes | No (search only) |
| Azure Cosmos DB (vector) | NoSQL + Vector | Yes | Limited relational |
| Pinecone | SaaS Vector DB | No (external) | No |
| Qdrant | Vector DB | No (self-hosted on AKS) | No |
| Weaviate | Vector DB | No (self-hosted on AKS) | No |

## Decision

We will use **Azure Database for PostgreSQL Flexible Server with the pgvector extension**
as our combined relational and vector database.

### Rationale

**1. Single database for relational and vector data**

PostgreSQL with pgvector serves both as our application database (relational tables for
users, sessions, configurations, audit logs) and our vector store (embedding tables with
HNSW or IVFFlat indexes). This eliminates the need to manage, pay for, and synchronize
two separate databases.

**2. Azure managed service with pgvector support**

Azure Database for PostgreSQL Flexible Server natively supports the pgvector extension.
Enabling it is a single configuration change:

```sql
CREATE EXTENSION vector;
```

We get automated backups, patching, high availability, and monitoring from the managed
service.

**3. Cost efficiency**

A single Burstable B1ms instance (~$30/month for Dev) handles both application and vector
workloads. Dedicated vector databases like Azure AI Search start at ~$70/month (Basic
tier) and provide only search functionality, requiring a separate database for application
data.

| Solution | Monthly Cost (Dev) | Monthly Cost (Prod) |
|----------|-------------------|---------------------|
| PostgreSQL Flexible Server (B1ms/D2ds_v5) | ~$30 | ~$200 |
| Azure AI Search (Basic) + PostgreSQL | ~$100 | ~$450+ |
| Cosmos DB (1000 RU/s) + vector | ~$60 | ~$400+ |
| Pinecone (Starter) + PostgreSQL | ~$100+ | ~$400+ |

**4. Familiar technology**

PostgreSQL is the most widely known relational database. Every team member can query it
with standard SQL. No need to learn a new query language or API for vector operations.

```sql
-- Vector similarity search with metadata filtering
SELECT id, content, metadata,
       embedding <=> $1::vector AS distance
FROM documents
WHERE department = 'manufacturing'
  AND created_at > '2026-01-01'
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

**5. ACID transactions**

Vector operations participate in PostgreSQL transactions. We can atomically insert a
document, its metadata, and its embedding in a single transaction, ensuring consistency.

**6. Mature indexing for our scale**

pgvector supports HNSW (Hierarchical Navigable Small World) indexes, which provide
excellent recall and query performance for up to low millions of vectors. Our expected
scale (hundreds of thousands of embeddings) is well within pgvector's sweet spot.

```sql
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

## Consequences

### Positive

- **Single managed service** for application data and vector embeddings.
- **Lowest operational overhead** -- one database to backup, monitor, and scale.
- **Lowest cost** -- no second database service needed.
- **Standard SQL** -- no new query language to learn.
- **ACID transactions** -- consistent data operations.
- **Azure-native** -- integrates with VNet, Private Endpoints, Entra ID, Key Vault.

### Negative

- **Performance ceiling** -- For very large vector datasets (tens of millions+), a
  dedicated vector database may outperform pgvector. Not a concern at our current scale.
- **Resource contention** -- Application queries and vector searches share compute. We
  mitigate this with proper connection pooling and read replicas if needed.
- **Limited vector-specific features** -- Dedicated vector DBs offer features like
  namespaces, automatic reindexing, and vector-specific sharding. pgvector's feature set
  is smaller but sufficient for our needs.
- **Index build time** -- HNSW index builds can be slow for large datasets (millions of
  vectors). Manageable at our scale, and we can build indexes during off-peak hours.

### Mitigations

- Monitor query performance and resource utilization via Azure Monitor.
- Use connection pooling (PgBouncer, built into Flexible Server) to manage connections.
- If vector workload grows significantly, consider adding a read replica dedicated to
  vector queries.
- If we outgrow pgvector's capabilities, migrate vector data to Azure AI Search while
  keeping PostgreSQL for relational data. The RAG pipeline abstraction layer makes this
  swap feasible.

## Alternatives Rejected

### Azure AI Search

Strong vector search capabilities with hybrid (keyword + vector) search. Rejected because:
- Requires a separate relational database for application data (doubled infrastructure)
- Higher cost for the combined solution
- Overkill for our initial scale
- Could be added later for hybrid search if keyword search becomes important

### Azure Cosmos DB (vector search)

Rejected because:
- Vector search in Cosmos DB is newer and less mature than pgvector
- Request Unit (RU) pricing model is harder to predict for mixed workloads
- NoSQL data model less suitable for our relational application data
- Higher cost at equivalent performance

### Pinecone / Qdrant / Weaviate

Dedicated vector databases rejected because:
- Not available as Azure managed services (Pinecone is SaaS, others need AKS)
- Require a separate relational database for application data
- Additional operational burden of managing non-Azure infrastructure
- Higher total cost of ownership
- Not justified at our scale
