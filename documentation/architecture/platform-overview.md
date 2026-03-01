# Azure Data Platform - Architecture Overview

## Table of Contents

- [Platform Vision and Goals](#platform-vision-and-goals)
- [Environment Strategy](#environment-strategy)
- [Management Group Hierarchy](#management-group-hierarchy)
- [Subscription Layout](#subscription-layout)
- [Resource Group Organization](#resource-group-organization)
- [Network Topology](#network-topology)
- [Data Architecture](#data-architecture)
- [AI Architecture](#ai-architecture)
- [Application Architecture](#application-architecture)
- [Security Model](#security-model)
- [Data Governance](#data-governance)
- [Cost Optimization Strategy](#cost-optimization-strategy)

---

## Platform Vision and Goals

This platform serves a manufacturing and sales company, providing a unified data and AI
foundation that enables:

1. **Unified Data Estate** -- Consolidate data from manufacturing systems, sales platforms,
   ERP, and operational sources into a single governed data platform on Microsoft Fabric.

2. **AI-Powered Insights** -- Leverage Azure AI Foundry and Fabric Data Agents to deliver
   intelligent search, anomaly detection, and predictive analytics across manufacturing
   and sales data.

3. **Data Governance** -- Establish enterprise data governance through Microsoft Purview,
   ensuring data quality, lineage tracking, and regulatory compliance.

4. **Self-Service Analytics** -- Empower business users with curated Gold-layer datasets
   and AI-powered natural language querying.

5. **Operational Excellence** -- Infrastructure as Code (Bicep), automated CI/CD, and
   environment parity across Dev, QA, and Prod.

### Design Principles

- **Subscription-per-environment** for strong isolation and cost visibility
- **Infrastructure as Code** exclusively via Bicep for Azure-native deployments
- **Least privilege access** with Entra ID RBAC and managed identities
- **Medallion architecture** (Bronze/Silver/Gold) for data processing
- **GitOps workflow** -- all changes flow through pull requests and CI/CD

---

## Environment Strategy

We use a **subscription-per-environment** model (see [ADR-001](../adr/001-subscription-per-environment.md)).

| Environment | Purpose | Subscription | Deployment |
|-------------|---------|-------------|------------|
| **Dev** | Development and experimentation | Sub-DataPlatform-NonProd | Automatic on merge to `main` |
| **QA** | Integration testing and UAT | Sub-DataPlatform-NonProd | Automatic after Dev succeeds |
| **Prod** | Production workloads | Sub-DataPlatform-Prod | Manual approval required |

**Rationale:**
- Hard subscription-level boundaries prevent Dev/QA resource leaks into Prod
- Independent RBAC, policy, and cost management per subscription
- Azure Policy enforced at the Management Group level for consistency
- Separate Azure quotas and rate limits per environment

---

## Management Group Hierarchy

```
Tenant Root Group
|
+-- mg-company-root
    |
    +-- mg-platform
    |   |
    |   +-- Sub-Platform
    |       (Shared services: DNS, monitoring, identity)
    |
    +-- mg-data-platform
        |
        +-- mg-data-nonprod
        |   |
        |   +-- Sub-DataPlatform-NonProd
        |       (Dev + QA environments)
        |
        +-- mg-data-prod
            |
            +-- Sub-DataPlatform-Prod
                (Production environment)
```

**Policy Assignment Strategy:**
- `mg-company-root` -- Allowed regions, required tags, diagnostic settings
- `mg-data-platform` -- Data-specific policies (encryption, network restrictions)
- `mg-data-prod` -- Stricter policies (no public endpoints, mandatory CMK)

---

## Subscription Layout

### Sub-Platform (Shared Services)

Hosts cross-cutting infrastructure shared across all environments:

| Resource Group | Contents |
|----------------|----------|
| `rg-networking-hub-eus2` | Hub VNet, Azure Firewall, VPN/ExpressRoute Gateway, Azure Bastion |
| `rg-identity-eus2` | Entra ID app registrations, managed identity resources |
| `rg-monitoring-eus2` | Log Analytics workspace, Application Insights, alert rules |
| `rg-dns-eus2` | Private DNS Zones for all Azure PaaS services |

### Sub-DataPlatform-NonProd (Dev + QA)

| Resource Group | Contents |
|----------------|----------|
| `rg-fabric-dev-eus2` | Fabric capacity (F2), Dev workspace configuration |
| `rg-fabric-qa-eus2` | Fabric capacity (F2), QA workspace configuration |
| `rg-purview-nonprod-eus2` | Purview account (shared across Dev/QA) |
| `rg-ai-dev-eus2` | AI Foundry hub, model deployments (Dev) |
| `rg-ai-qa-eus2` | AI Foundry hub, model deployments (QA) |
| `rg-data-dev-eus2` | PostgreSQL Flexible Server (pgvector), Redis Cache |
| `rg-data-qa-eus2` | PostgreSQL Flexible Server (pgvector), Redis Cache |
| `rg-apps-dev-eus2` | App Service Plan, Streamlit + React App Services |
| `rg-apps-qa-eus2` | App Service Plan, Streamlit + React App Services |
| `rg-networking-dev-eus2` | Dev spoke VNet, NSGs, peering to hub |
| `rg-networking-qa-eus2` | QA spoke VNet, NSGs, peering to hub |
| `rg-security-nonprod-eus2` | Key Vault, managed identities |

### Sub-DataPlatform-Prod (Production)

| Resource Group | Contents |
|----------------|----------|
| `rg-fabric-prod-eus2` | Fabric capacity (F4+), Prod workspace configuration |
| `rg-purview-prod-eus2` | Purview account (Prod) |
| `rg-ai-prod-eus2` | AI Foundry hub, model deployments (Prod) |
| `rg-data-prod-eus2` | PostgreSQL Flexible Server (pgvector), Redis Cache |
| `rg-apps-prod-eus2` | App Service Plan (P1v3+), Streamlit + React App Services |
| `rg-networking-prod-eus2` | Prod spoke VNet, NSGs, peering to hub |
| `rg-security-prod-eus2` | Key Vault, managed identities |

---

## Network Topology

We use a **hub-spoke** topology with the hub in the Platform subscription.

```
                          +---------------------------+
                          |     Sub-Platform (Hub)    |
                          |                           |
                          |  +---------------------+  |
                          |  |   Hub VNet           |  |
                          |  |   10.0.0.0/16        |  |
                Internet  |  |                       |  |
                   |      |  |  +-- Azure Firewall   |  |
                   v      |  |  |   10.0.1.0/24      |  |
            +----------+  |  |  |                     |  |
            | Azure FW |<--->|  +-- Bastion Subnet   |  |
            +----------+  |  |  |   10.0.2.0/24      |  |
                          |  |  |                     |  |
                          |  |  +-- GatewaySubnet    |  |
                          |  |      10.0.3.0/24      |  |
                          |  +---------------------+  |
                          +-----------|---|----------+
                                VNet  |   |  VNet
                              Peering |   | Peering
                   +------------------+   +------------------+
                   |                                          |
    +--------------v--------------+        +------------------v-----------+
    | Sub-DataPlatform-NonProd    |        | Sub-DataPlatform-Prod        |
    |                             |        |                              |
    | +-------------------------+ |        | +--------------------------+ |
    | | Dev Spoke VNet           | |        | | Prod Spoke VNet           | |
    | | 10.1.0.0/16              | |        | | 10.3.0.0/16               | |
    | |                          | |        | |                           | |
    | | +-- App Subnet           | |        | | +-- App Subnet            | |
    | | |   10.1.1.0/24          | |        | | |   10.3.1.0/24           | |
    | | |                        | |        | | |                         | |
    | | +-- Data Subnet          | |        | | +-- Data Subnet           | |
    | | |   10.1.2.0/24          | |        | | |   10.3.2.0/24           | |
    | | |                        | |        | | |                         | |
    | | +-- PE Subnet            | |        | | +-- PE Subnet             | |
    | |     10.1.3.0/24          | |        | |     10.3.3.0/24           | |
    | +-------------------------+ |        | +--------------------------+ |
    |                             |        |                              |
    | +-------------------------+ |        |                              |
    | | QA Spoke VNet            | |        |                              |
    | | 10.2.0.0/16              | |        |                              |
    | | (same subnet layout)     | |        |                              |
    | +-------------------------+ |        |                              |
    +-----------------------------+        +------------------------------+
```

**Key Network Design Decisions:**
- All PaaS services accessed via Private Endpoints (PE Subnet)
- Azure Firewall provides centralized egress filtering and FQDN rules
- No public endpoints in Prod (enforced by Azure Policy)
- Bastion for secure administrative access (no public RDP/SSH)
- DNS resolution via Azure Private DNS Zones linked to Hub VNet

---

## Data Architecture

### Medallion Architecture (Bronze / Silver / Gold)

Data flows through a three-tier Medallion architecture implemented in Microsoft Fabric.

```
+-------------------+     +-------------------+     +-------------------+
|    DATA SOURCES   |     |   MICROSOFT FABRIC LAKEHOUSE               |
|                   |     |                                             |
| Manufacturing     |     | +-------------+  +-------------+  +------+ |
|  - IoT Sensors    |---->| |   BRONZE    |->|   SILVER    |->| GOLD | |
|  - SCADA/MES      |     | |             |  |             |  |      | |
|  - Quality Data   |     | | Raw Ingest  |  | Cleansed    |  | Biz  | |
|                   |     | | - Parquet   |  | - Delta     |  | Agg  | |
| Sales             |     | | - JSON      |  | - Validated |  |      | |
|  - CRM/ERP        |---->| | - CSV       |  | - Conformed |  |      | |
|  - E-commerce     |     | | - API dumps |  | - Deduped   |  |      | |
|  - POS Systems    |     | +-------------+  +-------------+  +------+ |
|                   |     |       |                |              |     |
| External          |     |       v                v              v     |
|  - Market Data    |---->|  Data Pipelines   Notebooks      Semantic  |
|  - Supplier Feeds |     |  (Orchestration)  (Spark/Python)  Models   |
+-------------------+     +--------|---------------|-------------|-----+
                                   |               |             |
                          +--------|---------------|-------------|-------+
                          |  CONSUMPTION LAYER                          |
                          |                                             |
                          |  +-- Power BI (Semantic Models, Reports)    |
                          |  +-- AI Foundry (ML Models, Agents)         |
                          |  +-- Streamlit (Admin Dashboards)           |
                          |  +-- React App (Customer-facing)            |
                          |  +-- Purview (Governance, Lineage, Catalog) |
                          +---------------------------------------------+
```

### Data Layers

| Layer | Storage | Format | Purpose |
|-------|---------|--------|---------|
| **Bronze** | Fabric Lakehouse | Parquet, JSON, CSV | Raw data, append-only, full fidelity |
| **Silver** | Fabric Lakehouse | Delta | Cleansed, validated, conformed, deduped |
| **Gold** | Fabric Lakehouse | Delta | Business aggregates, star schemas, ML features |
| **Serving** | PostgreSQL (pgvector) | Relational + Vector | Application data, vector embeddings for RAG |

### Data Ingestion Patterns

| Source Type | Ingestion Method | Frequency |
|-------------|-----------------|-----------|
| Manufacturing IoT | Fabric Data Pipeline (Event Hub) | Near real-time |
| ERP/CRM | Fabric Data Pipeline (REST connector) | Hourly / Daily |
| Files (CSV/Excel) | Fabric OneLake shortcut / Upload | On-demand |
| External APIs | Fabric Notebook (Python) | Scheduled |

---

## AI Architecture

### RAG Pipeline: Fabric Data Agent + AI Foundry + pgvector

```
+------------------+     +--------------------+     +------------------+
|  DATA SOURCES    |     |  EMBEDDING LAYER   |     |  VECTOR STORE    |
|                  |     |                    |     |                  |
| Gold Layer Data  |---->| AI Foundry         |---->| PostgreSQL       |
| Documents (PDFs) |     | - Text Embedding   |     | + pgvector       |
| Knowledge Base   |     |   (ada-002 /       |     |                  |
| Manuals          |     |    text-embed-3)   |     | Stores:          |
+------------------+     +--------------------+     | - Embeddings     |
                                                    | - Metadata       |
                                                    | - Full text      |
                                                    +--------|---------+
                                                             |
                         +-----------------------------------v---------+
                         |  QUERY / INFERENCE LAYER                    |
                         |                                             |
User Query  ------------>|  1. Query embedding via AI Foundry          |
                         |  2. Vector similarity search (pgvector)     |
                         |  3. Context assembly (top-k chunks)         |
                         |  4. LLM completion (GPT-4o via AI Foundry)  |
                         |  5. Response with citations                 |
                         |                                             |
                         +---------------------------------------------+
                                             |
                         +-------------------v-------------------------+
                         |  FABRIC DATA AGENT                          |
                         |                                             |
                         |  - Natural language to SQL (Gold layer)     |
                         |  - Conversational analytics                 |
                         |  - Grounded in enterprise data catalog      |
                         |  - Governed by Purview policies             |
                         +---------------------------------------------+
```

### AI Components

| Component | Service | Purpose |
|-----------|---------|---------|
| Embedding Model | AI Foundry (text-embedding-3-small) | Generate vector embeddings for RAG |
| Chat Model | AI Foundry (GPT-4o) | Generate responses grounded in retrieved context |
| Vector Database | PostgreSQL + pgvector | Store and query vector embeddings |
| Data Agent | Fabric Data Agent | Natural language querying over structured data |
| Governance | Microsoft Purview | Classify, label, and govern AI training data |

---

## Application Architecture

```
+----------------------------------------------------------+
|  USERS                                                    |
|                                                           |
|  Internal (Admin)              External (Customers)       |
|       |                              |                    |
|       v                              v                    |
|  +-------------+              +--------------+            |
|  | Streamlit   |              | React Web    |            |
|  | Admin App   |              | App          |            |
|  | (Python)    |              | (TypeScript) |            |
|  +------+------+              +------+-------+            |
|         |                            |                    |
+---------|-----------+----------------|-----------+--------+
          |           |                |           |
          v           v                v           v
   +-----------+ +---------+   +-----------+ +---------+
   | AI Foundry| |PostgreSQL|   | AI Foundry| |Fabric   |
   | (Chat API)| |(pgvector)|   | (Chat API)| |REST API |
   +-----------+ +---------+   +-----------+ +---------+
```

### Streamlit Admin App

- **Purpose:** Internal admin dashboard for data platform management
- **Runtime:** Azure App Service (Linux container)
- **Auth:** Entra ID authentication (MSAL)
- **Features:**
  - Monitor data pipeline health and execution
  - Manage AI model deployments and prompt templates
  - View data quality metrics and anomaly alerts
  - Admin RAG chat interface for internal knowledge base
  - pgvector index management and embedding pipeline monitoring

### React Web App

- **Purpose:** Customer-facing web application
- **Runtime:** Azure App Service (Linux container)
- **Auth:** Entra ID B2C or Entra External ID
- **Features:**
  - AI-powered product search and recommendations
  - Order tracking with intelligent status updates
  - Self-service analytics dashboards (embedded Power BI)
  - Customer support chatbot (RAG-powered)

---

## Security Model

### Identity and Access Management

| Layer | Mechanism |
|-------|-----------|
| User Authentication | Entra ID (internal), Entra External ID (customers) |
| Service Authentication | Managed Identities (system and user-assigned) |
| CI/CD Authentication | Workload Identity Federation (OIDC, no secrets) |
| API Authorization | Entra ID app roles + OAuth 2.0 scopes |
| Data Authorization | Fabric workspace roles + Purview access policies |

### Network Security

- All PaaS services behind Private Endpoints
- Azure Firewall for centralized egress control
- NSGs on all subnets with deny-all default
- No public IP addresses in Prod (Azure Policy enforced)
- Azure Bastion for secure administrative access

### Data Security

| Control | Implementation |
|---------|---------------|
| Encryption at rest | Platform-managed keys (CMK for Prod) |
| Encryption in transit | TLS 1.2+ enforced everywhere |
| Secret management | Azure Key Vault with RBAC access policies |
| Data classification | Microsoft Purview sensitivity labels |
| Data masking | Dynamic data masking on PII columns |
| Audit logging | Diagnostic settings to Log Analytics |

### Compliance

- Azure Policy enforced at Management Group level
- Microsoft Defender for Cloud enabled
- Regular access reviews via Entra ID
- Purview data lineage for audit trail

---

## Data Governance

Data governance is implemented through Microsoft Purview, following the LivaNova
Fabric Development Framework (Section 5). See `documentation/runbooks/purview-governance.md`
for the full governance runbook.

### Governance Architecture

| Component | Purpose | Configuration |
|-----------|---------|---------------|
| Data Map | Automated discovery and scanning of data assets | `scripts/governance/` (SDK) |
| Unified Catalog | Searchable catalog with business glossary | Automated via SDK |
| Classifications | PII detection and custom data classification | Automated via SDK |
| Sensitivity Labels | Information protection labels | Compliance Portal (manual) |
| DLP Policies | Data loss prevention enforcement | Compliance Portal (manual) |
| Lineage | Source-to-report data lineage tracking | Automatic via Fabric/ADF |

### Governance Roles

| Role | Responsibility | Identity |
|------|---------------|----------|
| Data Curator | Manage catalog, approve access | `dp-id-platform-dev` (MI) |
| Data Source Admin | Register sources, configure scans | `dp-id-platform-dev` (MI) |
| Data Steward | Manage glossary, review classifications | Team members (Entra ID) |
| Compliance Officer | Manage sensitivity labels, DLP | Entra ID user (manual) |

### Separation of Concerns

**Key Principle:** Purview defines policies and metadata; Fabric enforces runtime access.

| Capability | Managed In | Rationale |
|------------|-----------|-----------|
| Data Catalog | Purview | Central catalog across all data sources |
| Data Lineage | Purview | End-to-end lineage including non-Fabric sources |
| Sensitivity Labels | Purview | Enterprise-wide label definitions |
| Data Classification | Purview | Automated scanning and labeling |
| Data Access Control | Fabric | Runtime access enforcement for Fabric data |
| Workspace Permissions | Fabric | Operational access to Fabric workloads |

### Custom Classifications

| Classification | Target Data | Compliance |
|---------------|-------------|-----------|
| CUSTOM_CUSTOMER_DATA | Customer PII (names, addresses, emails) | GDPR/CCPA |
| CUSTOM_FINANCIAL_DATA | Financial values (pricing, billing) | SOX |
| CUSTOM_EMPLOYEE_DATA | Employee data | Internal privacy |
| CUSTOM_MANUFACTURING_IP | Trade secrets (formulas, specs) | Competitive protection |
| CUSTOM_REGULATORY_DATA | Batch/lot tracking, quality | FDA/SEC/EMA |

---

## Cost Optimization Strategy

### Sizing Strategy

| Environment | Fabric SKU | PostgreSQL | App Service | AI Foundry |
|-------------|-----------|------------|-------------|------------|
| Dev | F2 | Burstable B1ms | B1 | Pay-as-you-go |
| QA | F2 | Burstable B2s | B2 | Pay-as-you-go |
| Prod | F4+ | GP D2ds_v5 | P1v3 | PTU (if justified) |

### Cost Controls

1. **Fabric Capacity Pause** -- Automatically pause Dev/QA Fabric capacities outside
   business hours (saves ~65% on compute).

2. **Right-sizing Reviews** -- Monthly review of resource utilization via Azure Advisor
   and Cost Management.

3. **Reserved Instances** -- 1-year reservations for Prod PostgreSQL and App Service
   once usage patterns stabilize.

4. **Dev/QA Shutdowns** -- Automated start/stop schedules for non-production resources:
   - Weekdays: 08:00-20:00 local time
   - Weekends: Off

5. **Budget Alerts** -- Azure Cost Management budgets with alerts at 50%, 80%, and 100%
   thresholds per subscription.

6. **Tag-based Cost Tracking** -- All resources tagged with:
   - `environment` (dev/qa/prod)
   - `project` (data-platform)
   - `cost-center` (assigned business unit)
   - `owner` (team or individual)

7. **AI Foundry Optimization** -- Use standard (pay-per-token) deployments in Dev/QA;
   evaluate Provisioned Throughput Units (PTU) for Prod when token volume justifies it.

### Estimated Monthly Costs (USD)

| Component | Dev | QA | Prod |
|-----------|-----|-----|------|
| Fabric (F2/F4) | ~$260 | ~$260 | ~$520+ |
| PostgreSQL | ~$30 | ~$50 | ~$200 |
| App Service | ~$15 | ~$30 | ~$150 |
| AI Foundry (tokens) | ~$50 | ~$50 | ~$200+ |
| Networking | ~$20 | ~$20 | ~$100 |
| Monitoring | ~$10 | ~$10 | ~$50 |
| **Total** | **~$385** | **~$420** | **~$1,220+** |

*Estimates assume capacity pause schedules for Dev/QA. Actual costs will vary with usage.*
