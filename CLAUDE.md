# CLAUDE.md - Project Context for AI Assistants

## Project Overview

This is an **Azure Data Platform** for a manufacturing and sales company. The platform
unifies data ingestion, processing, AI/ML, governance, and application delivery on
Microsoft Azure.

- **Repository:** https://github.com/vamshi455/AzureAI.git
- **Team size:** 4-10 people
- **Cloud:** Azure only (no multi-cloud)
- **IaC:** Bicep (not Terraform -- see ADR-002)

## Repository Structure

```
AzureAI/
  infra/                    # Bicep templates and modules
    main.bicep              # Root deployment (subscription-level)
    modules/                # Reusable Bicep modules
    parameters/             # Environment-specific .bicepparam files
      dev.bicepparam
      qa.bicepparam
      prod.bicepparam
  data-platform/            # Microsoft Fabric notebooks, pipelines, SQL
    notebooks/              # Jupyter/Fabric notebooks (.ipynb)
    pipelines/              # Data pipeline definitions (.json)
    sql/                    # SQL scripts
    tests/                  # Python unit tests for data logic
  apps/
    streamlit-admin/        # Streamlit admin dashboard (Python)
    react-webapp/           # React customer-facing web app (TypeScript)
  documentation/
    architecture/           # Architecture docs and diagrams
    adr/                    # Architecture Decision Records
    runbooks/               # Operational runbooks
  .github/
    workflows/              # GitHub Actions CI/CD workflows
    ISSUE_TEMPLATE/         # Issue templates (bug, feature, incident)
    PULL_REQUEST_TEMPLATE.md
```

## Environments

| Environment | Subscription | Purpose |
|-------------|-------------|---------|
| Dev | Sub-DataPlatform-NonProd | Development and experimentation |
| QA | Sub-DataPlatform-NonProd | Integration testing and UAT |
| Prod | Sub-DataPlatform-Prod | Production (manual approval for deployments) |

There is also a **Sub-Platform** subscription for shared services (hub networking,
DNS, monitoring).

## Key Azure Services

| Service | Purpose |
|---------|---------|
| Microsoft Fabric | Lakehouse (Bronze/Silver/Gold), data pipelines, notebooks |
| Microsoft Purview | Data governance, lineage, classification |
| Azure AI Foundry | LLM deployments (GPT-4o, embeddings), AI agents |
| PostgreSQL + pgvector | Application database and vector store for RAG |
| Azure App Service | Hosts Streamlit (admin) and React (customer) apps |
| Azure Key Vault | Secret management |
| Azure Virtual Network | Hub-spoke topology with Private Endpoints |

## Conventions

### Naming

All Azure resources follow the naming convention in
`documentation/architecture/naming-conventions.md`:

```
{prefix}-{service}-{environment}-{region}-{instance}
```

- Prefix: `dp` (data platform)
- Region: `eus2` (East US 2)
- Example: `psql-vector-prod-eus2`, `app-streamlit-dev-eus2`
- No-hyphen resources (Storage, Key Vault): concatenated, e.g., `kvdpprodeus2001`

### Bicep

- All infrastructure defined in `infra/` directory
- Subscription-level deployments via `main.bicep`
- Reusable modules in `infra/modules/`
- Environment parameters in `infra/parameters/<env>.bicepparam`
- Run `az bicep build --file <file>` to lint
- Run `az bicep format --file <file>` to format

### Python

- Python 3.11+
- Linting: `ruff check` and `ruff format`
- Testing: `pytest`
- Notebooks linted via `nbqa ruff`

### React / TypeScript

- Node.js 20+
- Linting: ESLint via `npm run lint`
- Testing: Jest via `npm test`
- Build: `npm run build`

### Git Workflow

- **Main branch:** `main` (protected, requires PR)
- **Branch naming:** `feature/description`, `fix/description`, `infra/description`
- **PR process:** All changes via PR with CI checks (see `.github/workflows/pr-checks.yml`)
- **Deployments:** Merge to `main` triggers deployment (Dev -> QA -> Prod with approval)

### CI/CD

- GitHub Actions for all CI/CD
- OIDC (Workload Identity Federation) for Azure authentication -- no stored secrets
- Environment protection rules on `prod` (manual approval required)
- Separate workflows for infra, data platform, and applications

## Architecture Decision Records

| ADR | Decision |
|-----|----------|
| 001 | Subscription-per-environment over resource-group-per-environment |
| 002 | Bicep over Terraform for IaC |
| 003 | PostgreSQL + pgvector for vector database (over Azure AI Search, Cosmos DB) |
| 004 | Plane for project ticketing (over Jira, Linear, GitHub Issues) |

ADRs are in `documentation/adr/`.

## Common Tasks

### Deploy infrastructure to Dev

```bash
az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam
```

### Run data platform tests

```bash
cd data-platform
pip install -r requirements.txt
pytest tests/ -v
```

### Run Streamlit app locally

```bash
cd apps/streamlit-admin
pip install -r requirements.txt
streamlit run app.py
```

### Run React app locally

```bash
cd apps/react-webapp
npm install
npm run dev
```

## Security Notes

- Never commit secrets, keys, or connection strings to the repository
- Use Azure Key Vault for all secrets
- Use managed identities for service-to-service authentication
- Use OIDC (federated credentials) for CI/CD -- no client secrets in GitHub
- All PaaS services use Private Endpoints in production
- See `.gitignore` for excluded secret file patterns

## Ticketing

We use **Plane** (self-hosted) for project management and sprint planning.
GitHub Issues are used for code-specific bug reports and incidents via the templates
in `.github/ISSUE_TEMPLATE/`.

## Key Documentation

- Architecture overview: `documentation/architecture/platform-overview.md`
- Naming conventions: `documentation/architecture/naming-conventions.md`
- Environment setup: `documentation/runbooks/environment-setup.md`
- Incident response: `documentation/runbooks/incident-response.md`
