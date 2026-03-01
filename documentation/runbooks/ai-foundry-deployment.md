# AI Foundry Deployment Runbook

## Overview

This runbook covers deploying Azure AI Foundry infrastructure and the Equipment Health Agent for the Manufacturing & Sales Data Platform.

## Prerequisites

- Azure CLI with active subscription (`az login`)
- Bicep CLI (`az bicep install`)
- Python 3.11+ with pip
- Access to `dp-rg-dev` resource group
- Existing resources: VNet, Key Vault, Log Analytics, App Insights, Platform Identity

## Phase 1: Deploy AI Foundry Infrastructure

### Deploy the Bicep module

```bash
az deployment group create \
  --resource-group dp-rg-dev \
  --name ai-foundry-deploy \
  --template-file infra/modules/ai-foundry/main.bicep \
  --parameters \
    location=eastus2 \
    environment=dev \
    resourcePrefix=dp \
    tags='{"project":"data-platform","environment":"dev"}' \
    privateEndpointSubnetId='<snet-private-endpoints-id>' \
    logAnalyticsWorkspaceId='<dp-log-dev-id>' \
    keyVaultId='<dp-kv-dev-id>' \
    applicationInsightsId='<dp-appi-dev-id>' \
    platformIdentityId='<dp-id-platform-dev-id>' \
    publicNetworkAccess=Enabled
```

### Resources created

| Resource | Name | Type |
|----------|------|------|
| AI Hub | `dp-aih-dev` | Microsoft.MachineLearningServices/workspaces (Hub) |
| AI Project | `dp-aip-mfg-sales-dev` | Microsoft.MachineLearningServices/workspaces (Project) |
| Storage Account | `dpstaidev*` | AI Foundry blob storage |
| Container Registry | `dpcraidev*` | Premium ACR |
| Private Endpoints | 3x | Hub, CR, Storage blob |

## Phase 2: Deploy Azure OpenAI + Models

### Register resource provider (if needed)

```bash
az provider register --namespace Microsoft.CognitiveServices
az provider show -n Microsoft.CognitiveServices --query registrationState
```

### Create Azure OpenAI resource

```bash
az cognitiveservices account create \
  --name dp-aoai-dev \
  --resource-group dp-rg-dev \
  --kind OpenAI \
  --sku S0 \
  --location eastus2 \
  --custom-domain dp-aoai-dev
```

### Deploy models

```bash
# GPT-4o for agent reasoning
az cognitiveservices account deployment create \
  --name dp-aoai-dev \
  --resource-group dp-rg-dev \
  --deployment-name gpt-4o-equipment-health \
  --model-name gpt-4o \
  --model-version "2025-05-13" \
  --model-format OpenAI \
  --sku-name Standard \
  --sku-capacity 150

# Embedding model for RAG
az cognitiveservices account deployment create \
  --name dp-aoai-dev \
  --resource-group dp-rg-dev \
  --deployment-name text-embedding-3-large-rag \
  --model-name text-embedding-3-large \
  --model-version "1" \
  --model-format OpenAI \
  --sku-name Standard \
  --sku-capacity 350
```

### RBAC for platform identity

```bash
AOAI_ID=$(az cognitiveservices account show --name dp-aoai-dev -g dp-rg-dev --query id -o tsv)
PRINCIPAL_ID=<platform-identity-principal-id>

az role assignment create \
  --role "Cognitive Services OpenAI User" \
  --assignee-object-id $PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --scope $AOAI_ID
```

## Phase 3: Deploy PostgreSQL + Load Data

### Deploy PostgreSQL Flexible Server

```bash
az deployment group create \
  --resource-group dp-rg-dev \
  --name postgresql-dev \
  --template-file infra/modules/postgresql/main.bicep \
  --parameters \
    location=eastus2 environment=dev resourcePrefix=dp \
    administratorLogin=dpadmin \
    administratorPassword='<secure-password>' \
    skuName=Standard_B1ms storageSizeGB=32 \
    dataSubnetId='<snet-data-id>' \
    privateDnsZoneId='<postgres-dns-zone-id>' \
    logAnalyticsWorkspaceId='<log-analytics-id>'
```

### Load equipment data

```bash
cd scripts/ai
pip install pandas psycopg2-binary pyarrow

export PGHOST=dp-psql-dev.postgres.database.azure.com
export PGDATABASE=manufacturing_db
export PGUSER=dpadmin
export PGPASSWORD='<password>'
export PGSSLMODE=require

python load_equipment_data.py
```

Expected output:
- `equipment_health`: ~200 rows
- `iot_telemetry`: ~500K rows
- `equipment_lifecycle_events`: varies

## Phase 4: Index Equipment Health Docs

```bash
export AZURE_OPENAI_ENDPOINT=https://dp-aoai-dev.openai.azure.com/
export AZURE_OPENAI_API_KEY=<key>

python index_equipment_docs.py \
  --pg-host dp-psql-dev.postgres.database.azure.com \
  --pg-dbname vector_db \
  --pg-user dpadmin \
  --pg-password '<password>'
```

Expected: ~180+ documents indexed into `document_embeddings` table.

## Phase 5: Verify

```bash
# Check AI Foundry
az resource show --ids /subscriptions/.../workspaces/dp-aih-dev --query properties.provisioningState

# Check OpenAI models
az cognitiveservices account deployment list --name dp-aoai-dev -g dp-rg-dev -o table

# Check PostgreSQL data
psql "host=dp-psql-dev.postgres.database.azure.com dbname=manufacturing_db user=dpadmin sslmode=require" \
  -c "SELECT count(*) FROM equipment_health; SELECT count(*) FROM iot_telemetry;"

# Check pgvector index
psql "host=dp-psql-dev.postgres.database.azure.com dbname=vector_db user=dpadmin sslmode=require" \
  -c "SELECT count(*) FROM document_embeddings WHERE document_type='equipment_health';"

# Test agent API
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "equipment-health-agent",
    "messages": [{"role": "user", "content": "What is the health status of EQ-1100-A-006?"}]
  }'
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| CognitiveServices provider not registered | `az provider register --namespace Microsoft.CognitiveServices` (takes ~5 min) |
| PostgreSQL VNet integration fails | Ensure `snet-data` is delegated to `Microsoft.DBforPostgreSQL/flexibleServers` |
| Embedding API 401 | Check RBAC: platform identity needs `Cognitive Services OpenAI User` on the AOAI resource |
| Agent returns 503 | `PGVECTOR_CONNECTION_STRING` env var not set in API |
