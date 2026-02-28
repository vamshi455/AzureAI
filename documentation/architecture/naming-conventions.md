# Azure Resource Naming Conventions

## Overview

This document defines the naming standard for all Azure resources in the Data Platform.
Consistent naming enables easier resource identification, cost tracking, and policy enforcement.

## General Format

```
{prefix}-{service}-{environment}-{region}-{instance}
```

| Segment | Description | Example |
|---------|-------------|---------|
| `{prefix}` | Company or project abbreviation | `dp` (data platform) |
| `{service}` | Short code for the Azure service | `psql`, `kv`, `vnet` |
| `{environment}` | Deployment environment | `dev`, `qa`, `prod` |
| `{region}` | Azure region short code | `eus2` (East US 2) |
| `{instance}` | Numeric instance identifier (optional) | `001`, `002` |

### Rules

1. Use **lowercase** letters, numbers, and hyphens only (where the resource allows hyphens).
2. No trailing hyphens or consecutive hyphens.
3. Keep names under the Azure resource name length limit (varies by service).
4. Some resources (Storage Accounts, Key Vaults) do not allow hyphens -- use concatenation.
5. Instance numbers start at `001`.

### Region Short Codes

| Azure Region | Short Code |
|--------------|-----------|
| East US 2 | `eus2` |
| Central US | `cus` |
| West US 2 | `wus2` |
| West Europe | `weu` |
| North Europe | `neu` |

---

## Resource Group Naming

**Format:** `rg-{function}-{environment}-{region}`

| Example | Description |
|---------|-------------|
| `rg-fabric-dev-eus2` | Fabric resources for Dev |
| `rg-fabric-qa-eus2` | Fabric resources for QA |
| `rg-fabric-prod-eus2` | Fabric resources for Prod |
| `rg-data-dev-eus2` | Data services (PostgreSQL, etc.) for Dev |
| `rg-apps-prod-eus2` | Application services for Prod |
| `rg-networking-hub-eus2` | Hub networking resources |
| `rg-security-nonprod-eus2` | Security resources for non-prod |

---

## Naming by Resource Type

### Networking

| Resource | Format | Example | Max Length |
|----------|--------|---------|-----------|
| Virtual Network | `vnet-{function}-{env}-{region}` | `vnet-hub-prod-eus2` | 64 |
| Subnet | `snet-{function}-{env}-{region}` | `snet-app-prod-eus2` | 80 |
| Network Security Group | `nsg-{function}-{env}-{region}` | `nsg-app-prod-eus2` | 80 |
| Route Table | `rt-{function}-{env}-{region}` | `rt-spoke-prod-eus2` | 80 |
| Azure Firewall | `afw-{function}-{region}` | `afw-hub-eus2` | 56 |
| Public IP | `pip-{function}-{env}-{region}` | `pip-afw-hub-eus2` | 80 |
| Private Endpoint | `pe-{target}-{env}-{region}` | `pe-psql-prod-eus2` | 80 |
| Private DNS Zone | Azure standard names | `privatelink.postgres.database.azure.com` | -- |
| VNet Peering | `peer-{source}-to-{target}` | `peer-hub-to-spoke-dev` | 80 |
| Azure Bastion | `bas-{function}-{region}` | `bas-hub-eus2` | 80 |

### Compute and Applications

| Resource | Format | Example | Max Length |
|----------|--------|---------|-----------|
| App Service Plan | `asp-{function}-{env}-{region}` | `asp-apps-prod-eus2` | 40 |
| App Service (Streamlit) | `app-streamlit-{env}-{region}` | `app-streamlit-prod-eus2` | 60 |
| App Service (React) | `app-react-{env}-{region}` | `app-react-prod-eus2` | 60 |
| Container Registry | `cr{prefix}{env}{region}` | `crdpprodeus2` | 50 (no hyphens) |

### Data Services

| Resource | Format | Example | Max Length |
|----------|--------|---------|-----------|
| PostgreSQL Flexible Server | `psql-{function}-{env}-{region}` | `psql-vector-prod-eus2` | 63 |
| PostgreSQL Database | `db-{function}-{env}` | `db-embeddings-prod` | 63 |
| Redis Cache | `redis-{function}-{env}-{region}` | `redis-cache-prod-eus2` | 63 |

### Microsoft Fabric

| Resource | Format | Example |
|----------|--------|---------|
| Fabric Capacity | `fc-{prefix}-{env}-{region}` | `fc-dp-prod-eus2` |
| Fabric Workspace | `ws-{function}-{env}` | `ws-lakehouse-prod` |
| Lakehouse | `lh-{layer}-{env}` | `lh-bronze-prod`, `lh-silver-prod`, `lh-gold-prod` |
| Notebook | `nb-{pipeline}-{step}` | `nb-sales-ingest`, `nb-mfg-transform` |
| Data Pipeline | `pl-{source}-{layer}` | `pl-erp-bronze`, `pl-bronze-silver` |
| Semantic Model | `sm-{domain}-{env}` | `sm-sales-prod`, `sm-manufacturing-prod` |

### AI and Machine Learning

| Resource | Format | Example | Max Length |
|----------|--------|---------|-----------|
| AI Foundry Hub | `aih-{prefix}-{env}-{region}` | `aih-dp-prod-eus2` | 64 |
| AI Foundry Project | `aip-{function}-{env}` | `aip-rag-prod` | 64 |
| Model Deployment | `deploy-{model}-{version}` | `deploy-gpt4o-v1` | 64 |
| AI Search | `srch-{prefix}-{env}-{region}` | `srch-dp-prod-eus2` | 60 |

### Governance

| Resource | Format | Example | Max Length |
|----------|--------|---------|-----------|
| Purview Account | `pview-{prefix}-{env}-{region}` | `pview-dp-prod-eus2` | 63 |

### Security

| Resource | Format | Example | Max Length |
|----------|--------|---------|-----------|
| Key Vault | `kv{prefix}{env}{region}{inst}` | `kvdpprodeus2001` | 24 (no hyphens) |
| Managed Identity (User) | `id-{function}-{env}-{region}` | `id-fabric-prod-eus2` | 128 |
| Managed Identity (CI/CD) | `id-cicd-{env}-{region}` | `id-cicd-prod-eus2` | 128 |

### Monitoring

| Resource | Format | Example | Max Length |
|----------|--------|---------|-----------|
| Log Analytics Workspace | `law-{prefix}-{env}-{region}` | `law-dp-prod-eus2` | 63 |
| Application Insights | `appi-{app}-{env}-{region}` | `appi-streamlit-prod-eus2` | 255 |
| Action Group | `ag-{function}-{env}` | `ag-alerts-prod` | 260 |

### Storage

| Resource | Format | Example | Max Length |
|----------|--------|---------|-----------|
| Storage Account | `st{prefix}{function}{env}{region}` | `stdpdiagprodeus2` | 24 (no hyphens, lowercase) |

---

## Tagging Standard

All resources must include the following tags:

| Tag Key | Required | Example Values | Purpose |
|---------|----------|---------------|---------|
| `environment` | Yes | `dev`, `qa`, `prod` | Environment identification |
| `project` | Yes | `data-platform` | Project association |
| `cost-center` | Yes | `engineering`, `data-team` | Cost allocation |
| `owner` | Yes | `data-platform-team` | Team ownership |
| `managed-by` | Yes | `bicep`, `manual` | IaC tracking |
| `created-date` | Yes | `2026-02-28` | Creation date |
| `criticality` | Prod only | `high`, `medium`, `low` | Business criticality |

### Tag Enforcement

Tags are enforced via Azure Policy at the `mg-data-platform` Management Group level:
- `environment`, `project`, `cost-center`, `owner` are required on all resources
- `managed-by` is required to track IaC vs. manual resource creation
- Non-compliant resources are flagged but not denied (audit mode initially)

---

## Examples (Complete Resource Names)

```
# Networking
vnet-hub-prod-eus2
snet-app-prod-eus2
nsg-data-prod-eus2
pe-psql-prod-eus2

# Compute
asp-apps-prod-eus2
app-streamlit-prod-eus2
app-react-prod-eus2

# Data
psql-vector-prod-eus2
redis-cache-prod-eus2

# Fabric
fc-dp-prod-eus2
ws-lakehouse-prod
lh-gold-prod

# AI
aih-dp-prod-eus2
aip-rag-prod

# Security
kvdpprodeus2001
id-fabric-prod-eus2

# Monitoring
law-dp-prod-eus2
appi-streamlit-prod-eus2
```
