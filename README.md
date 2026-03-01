# Azure Data Platform — Manufacturing & Sales

A production-grade Azure data platform that unifies data ingestion, AI/ML, governance, and application delivery for manufacturing and sales operations.

## Architecture

```
SAP ERP ──────┐
               │     ┌──────────────────────────────────────────────┐
Salesforce CRM ├────→│  ADLS Gen2 Lakehouse (Medallion Architecture) │
               │     │  Bronze → Silver → Gold → RAG Documents       │
IoT Sensors ──┘     └──────────────┬───────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              Predictive     Customer 360    AI/RAG Agents
              Maintenance    Analytics       (Equipment Health)
                    │              │              │
                    └──────────────┼──────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │  Applications                 │
                    │  Streamlit Admin + React Web  │
                    └──────────────────────────────┘
                                   ▲
                    ┌──────────────┴──────────────┐
                    │  Microsoft Purview            │
                    │  Data Catalog · PII Detection │
                    │  Business Glossary · DLP      │
                    └──────────────────────────────┘
```

## Key Services

| Service | Purpose |
|---------|---------|
| **Microsoft Fabric** | Lakehouse (Bronze/Silver/Gold), data pipelines, Spark notebooks |
| **Microsoft Purview** | Data governance, lineage, classification, business glossary |
| **Azure AI Foundry** | LLM deployments (GPT-4o, embeddings), AI agents |
| **PostgreSQL + pgvector** | Application database and vector store for RAG |
| **Azure App Service** | Hosts Streamlit (admin) and React (customer) apps |
| **Azure Key Vault** | Secret management |
| **Azure Virtual Network** | Hub-spoke topology with private endpoints |

## Repository Structure

```
AzureAI/
├── infra/                       # Bicep IaC (11 modules)
│   ├── main.bicep               #   Subscription-level orchestrator
│   ├── modules/                 #   networking, storage, postgresql, purview, ...
│   └── environments/            #   dev/, qa/, prod/ parameters
├── data-platform/               # Data pipelines & processing
│   ├── notebooks/               #   Spark notebooks (ML, transforms)
│   ├── pipelines/               #   Pipeline definitions (JSON)
│   ├── sql/                     #   SQL scripts
│   ├── schemas/                 #   Data model definitions
│   └── synthetic-data/          #   1.5M+ row data generators
├── ai/                          # AI/ML components
│   ├── agents/                  #   AI agent definitions
│   ├── rag/                     #   RAG pipeline (indexing + retrieval)
│   ├── models/                  #   Model deployment configs
│   └── prompts/                 #   Prompt templates
├── apps/                        # Applications
│   ├── admin-portal/            #   Streamlit dashboard (Python)
│   ├── web-app/                 #   React customer app (TypeScript)
│   └── api/                     #   Backend API
├── scripts/                     # Operational scripts
│   └── governance/              #   Purview governance automation
├── documentation/               # Architecture, ADRs, runbooks
└── .github/                     # CI/CD workflows
```

## Environments

| Environment | Subscription | Deployment |
|-------------|-------------|------------|
| **Dev** | Sub-DataPlatform-NonProd | Automatic on merge to `main` |
| **QA** | Sub-DataPlatform-NonProd | Automatic after Dev succeeds |
| **Prod** | Sub-DataPlatform-Prod | Manual approval required |

## Quick Start

### Prerequisites

- Azure CLI (`az`) with active subscription
- Python 3.11+
- Node.js 20+
- Bicep CLI (`az bicep install`)

### Deploy Infrastructure (Dev)

```bash
az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters infra/environments/dev/main.bicepparam
```

### Generate Synthetic Data

```bash
cd data-platform/synthetic-data
pip install -r requirements.txt
python generate_all.py            # 1.5M+ rows across 8 datasets
python upload_to_lakehouse.py     # Upload to ADLS Gen2
```

### Configure Purview Governance

```bash
cd scripts/governance
pip install -r requirements.txt
python run_all.py                 # Register sources, scans, glossary, classifications
python verify_governance.py       # Verify all configuration
```

### Run Applications Locally

```bash
# Streamlit admin dashboard
cd apps/admin-portal
pip install -r requirements.txt
streamlit run app.py

# React web app
cd apps/web-app
npm install && npm run dev
```

### Run Tests

```bash
# Python
cd data-platform && pip install -r requirements.txt && pytest tests/ -v

# React
cd apps/web-app && npm test

# Bicep lint
az bicep build --file infra/main.bicep
```

## Data Platform

### Synthetic Data (8 Datasets, 1.5M+ Rows)

| Source | Dataset | Rows | Key Fields |
|--------|---------|------|------------|
| SAP ERP | Customers | 10K | KUNNR, NAME1, STRAS |
| SAP ERP | Materials | 5K | MATNR, MAKTX, MTART |
| SAP ERP | Sales Orders | 50K | VBELN, KUNNR, NETWR |
| SAP ERP | Order Line Items | 150K | VBELN, MATNR, KWMENG |
| Salesforce | Accounts | 10K | AccountId, Name, Industry |
| Salesforce | Contacts | 25K | ContactId, Email, Phone |
| Salesforce | Opportunities | 30K | OpportunityId, Amount, Stage |
| IoT | Equipment Telemetry | 500K+ | EquipmentId, Temperature, Vibration |

### ML Pipeline

- **Predictive Maintenance**: Random Forest classifier on IoT telemetry
- **Features**: Rolling averages, vibration trends, temperature anomalies
- **Output**: Equipment health scores and failure risk in Gold layer

### RAG Pipeline

- **Equipment Health RAG**: Chunks maintenance manuals and specs
- **Hybrid chunking**: Section-based for manuals, fixed-size with overlap for specs
- **Vector store**: PostgreSQL + pgvector for semantic search

## Data Governance

Microsoft Purview configured with automated SDK scripts:

| Component | Details |
|-----------|---------|
| **Data Sources** | ADLS Gen2 lakehouse, PostgreSQL vector DB |
| **Scans** | Weekly (Sunday 2 AM UTC), Parquet/JSON/CSV/Delta |
| **Business Glossary** | 20 terms across 4 categories (SAP, CRM, IoT, Platform) |
| **Custom Classifications** | Customer, Financial, Employee, Manufacturing IP, Regulatory |
| **Built-in SITs** | Credit card, SSN, email, phone, driver's license, passport, medical record |
| **Sensitivity Labels** | Public → General → Confidential → Highly Confidential → Restricted |

See [purview-governance.md](documentation/runbooks/purview-governance.md) for the full governance runbook.

## Infrastructure Modules

| Module | Resource | Status |
|--------|----------|--------|
| networking | Hub-spoke VNet, NSGs, private DNS | Deployed |
| storage | ADLS Gen2 (Bronze/Silver/Gold/RAG) | Deployed |
| identity | Managed identity, RBAC | Deployed |
| monitoring | Log Analytics, diagnostics | Deployed |
| keyvault | Key Vault with private endpoint | Deployed |
| postgresql | PostgreSQL Flex + pgvector | Deployed |
| purview | Purview + private endpoints | Deployed |
| app-service | App Service Plan + web apps | Optional |
| ai-foundry | AI Foundry (GPT-4o, embeddings) | Optional |
| fabric | Microsoft Fabric capacity | Optional |
| plane | Plane ticketing (self-hosted) | Optional |

Enable optional modules via parameter flags:

```bash
az deployment sub create --location eastus2 --template-file infra/main.bicep \
  --parameters environment='dev' \
  enableStorage=true enablePurview=true enablePostgresql=true \
  enableAppService=false enableAIFoundry=false enableFabric=false enablePlane=false
```

## CI/CD

GitHub Actions with OIDC authentication (no stored secrets):

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `pr-checks.yml` | Pull request | Bicep lint, Python lint/test, React lint/test, security scan |
| `infra-deploy.yml` | Merge to main | Infrastructure deployment (Dev → QA → Prod) |
| `data-pipeline-ci.yml` | Merge to main | Data pipeline CI |
| `app-deploy.yml` | Merge to main | Application deployment |

## Security

- All PaaS services use **private endpoints** (no public internet exposure)
- **OIDC** (Workload Identity Federation) for CI/CD — no stored secrets
- **Managed identities** for service-to-service authentication
- **Key Vault** for all secrets and connection strings
- **Purview** for PII detection and data classification
- **Trivy** security scanning in CI pipeline

## Architecture Decisions

| ADR | Decision |
|-----|----------|
| [001](documentation/adr/001-subscription-per-environment.md) | Subscription-per-environment over resource-group-per-environment |
| [002](documentation/adr/002-bicep-over-terraform.md) | Bicep over Terraform for IaC |
| [003](documentation/adr/003-postgresql-pgvector.md) | PostgreSQL + pgvector for vector database |
| [004](documentation/adr/004-plane-ticketing.md) | Plane for project ticketing |
| [005](documentation/adr/005-purview-governance-automation.md) | Hybrid SDK + portal approach for Purview governance |

## Documentation

- [Platform Overview](documentation/architecture/platform-overview.md) — Full architecture reference
- [Naming Conventions](documentation/architecture/naming-conventions.md) — Resource naming standards
- [Topology Diagram](documentation/architecture/topology-diagram.md) — Deployed infrastructure visualization
- [Data Models](documentation/data-models/source-systems.md) — Source system schemas
- [Environment Setup](documentation/runbooks/environment-setup.md) — Step-by-step setup guide
- [Purview Governance](documentation/runbooks/purview-governance.md) — Governance runbook
- [Incident Response](documentation/runbooks/incident-response.md) — Incident handling procedures

## Contributing

1. Create a feature branch: `git checkout -b feature/description`
2. Make changes and ensure tests pass
3. Submit a PR — CI checks run automatically (lint, test, security scan)
4. All PRs require review before merge to `main`

Branch naming: `feature/`, `fix/`, `infra/`, `data/`, `docs/`

## License

Private repository. All rights reserved.
