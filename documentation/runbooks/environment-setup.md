# Runbook: New Environment Setup

## Purpose

Step-by-step guide for setting up a new environment (Dev, QA, or Prod) for the Azure
Data Platform. This covers Azure subscription configuration, OIDC federation for CI/CD,
Bicep deployment, and post-deployment verification.

---

## Prerequisites

Before starting, ensure you have:

- [ ] Azure subscription created and assigned to the correct Management Group
- [ ] Global Administrator or Owner role on the target subscription
- [ ] Azure CLI installed (`az --version >= 2.60`)
- [ ] Bicep CLI installed (`az bicep install`)
- [ ] GitHub repository admin access
- [ ] Access to the Platform (Hub) subscription for VNet peering

### Required Tools

```bash
# Verify tool versions
az --version          # Azure CLI 2.60+
az bicep version      # Bicep 0.30+
gh --version          # GitHub CLI 2.40+
```

---

## Step 1: Subscription Configuration

### 1.1 Register Required Resource Providers

```bash
SUBSCRIPTION_ID="<target-subscription-id>"
az account set --subscription "$SUBSCRIPTION_ID"

# Register resource providers
PROVIDERS=(
  "Microsoft.Fabric"
  "Microsoft.Purview"
  "Microsoft.CognitiveServices"
  "Microsoft.DBforPostgreSQL"
  "Microsoft.Web"
  "Microsoft.Network"
  "Microsoft.KeyVault"
  "Microsoft.ManagedIdentity"
  "Microsoft.OperationalInsights"
  "Microsoft.Insights"
  "Microsoft.ContainerRegistry"
  "Microsoft.Storage"
)

for provider in "${PROVIDERS[@]}"; do
  echo "Registering $provider..."
  az provider register --namespace "$provider" --wait
done

# Verify all providers are registered
az provider list --query "[?registrationState=='Registered'].namespace" -o tsv | sort
```

### 1.2 Assign Subscription to Management Group

```bash
ENV="dev"  # Change to: dev, qa, or prod

if [ "$ENV" == "prod" ]; then
  MG_NAME="mg-data-prod"
else
  MG_NAME="mg-data-nonprod"
fi

az account management-group subscription add \
  --name "$MG_NAME" \
  --subscription "$SUBSCRIPTION_ID"
```

### 1.3 Apply Subscription-Level Tags

```bash
az tag create --resource-id "/subscriptions/$SUBSCRIPTION_ID" --tags \
  environment="$ENV" \
  project="data-platform" \
  managed-by="bicep"
```

---

## Step 2: Set Up OIDC Authentication for GitHub Actions

### 2.1 Create Entra ID App Registration

```bash
APP_NAME="sp-cicd-dataplatform-$ENV"

# Create the app registration
APP_ID=$(az ad app create \
  --display-name "$APP_NAME" \
  --query appId -o tsv)

echo "App ID: $APP_ID"

# Create the service principal
SP_OBJECT_ID=$(az ad sp create \
  --id "$APP_ID" \
  --query id -o tsv)

echo "Service Principal Object ID: $SP_OBJECT_ID"
```

### 2.2 Configure Federated Credential (OIDC)

```bash
GITHUB_ORG="vamshi455"
GITHUB_REPO="AzureAI"

# Federated credential for the environment
cat <<EOF > federated-credential.json
{
  "name": "github-$ENV",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:${GITHUB_ORG}/${GITHUB_REPO}:environment:${ENV}",
  "description": "GitHub Actions OIDC for $ENV environment",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF

az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters federated-credential.json

# Additional credential for main branch (for workflows not using environments)
cat <<EOF > federated-credential-branch.json
{
  "name": "github-main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:${GITHUB_ORG}/${GITHUB_REPO}:ref:refs/heads/main",
  "description": "GitHub Actions OIDC for main branch",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF

az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters federated-credential-branch.json

rm federated-credential.json federated-credential-branch.json
```

### 2.3 Assign RBAC Roles

```bash
# Contributor on the subscription (for resource deployment)
az role assignment create \
  --assignee "$SP_OBJECT_ID" \
  --role "Contributor" \
  --scope "/subscriptions/$SUBSCRIPTION_ID"

# User Access Administrator (for managed identity role assignments)
az role assignment create \
  --assignee "$SP_OBJECT_ID" \
  --role "User Access Administrator" \
  --scope "/subscriptions/$SUBSCRIPTION_ID"
```

### 2.4 Configure GitHub Environment Secrets

```bash
TENANT_ID=$(az account show --query tenantId -o tsv)

echo "Configure these secrets in GitHub Environment '$ENV':"
echo "  AZURE_CLIENT_ID:       $APP_ID"
echo "  AZURE_TENANT_ID:       $TENANT_ID"
echo "  AZURE_SUBSCRIPTION_ID: $SUBSCRIPTION_ID"

# Using GitHub CLI (if you have admin access):
gh secret set AZURE_CLIENT_ID --env "$ENV" --body "$APP_ID"
gh secret set AZURE_TENANT_ID --env "$ENV" --body "$TENANT_ID"
gh secret set AZURE_SUBSCRIPTION_ID --env "$ENV" --body "$SUBSCRIPTION_ID"
```

### 2.5 Configure GitHub Environment Protection Rules

For **prod** environment only:

1. Go to GitHub repo > Settings > Environments > `prod`
2. Enable **Required reviewers** and add at least one team member
3. Enable **Wait timer** (optional, e.g., 5 minutes)
4. Restrict deployment branches to `main` only

---

## Step 3: Create Bicep Parameter File

### 3.1 Create Environment-Specific Parameters

Create the parameter file at `infra/parameters/<env>.bicepparam`:

```bicep
using '../main.bicep'

param environment = '<env>'
param location = 'eastus2'
param projectName = 'dp'

// Fabric
param fabricCapacitySku = '<env>' == 'prod' ? 'F4' : 'F2'

// PostgreSQL
param postgresqlSku = '<env>' == 'prod' ? 'GP_Standard_D2ds_v5' : 'B_Standard_B1ms'
param postgresqlStorageGb = <env> == 'prod' ? 128 : 32

// App Service
param appServicePlanSku = '<env>' == 'prod' ? 'P1v3' : 'B1'

// Networking
param vnetAddressPrefix = '<env-specific-CIDR>'
param hubVnetId = '/subscriptions/<platform-sub-id>/resourceGroups/rg-networking-hub-eus2/providers/Microsoft.Network/virtualNetworks/vnet-hub-prod-eus2'
```

---

## Step 4: Deploy Infrastructure

### 4.1 Validate the Deployment

```bash
az deployment sub validate \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters "infra/parameters/$ENV.bicepparam" \
  --name "validate-$ENV-manual"
```

### 4.2 Run What-If Preview

```bash
az deployment sub what-if \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters "infra/parameters/$ENV.bicepparam" \
  --name "whatif-$ENV-manual"
```

Review the output carefully. Confirm:
- [ ] No unexpected resource deletions
- [ ] Resource names follow naming conventions
- [ ] Correct SKUs for the target environment
- [ ] VNet address space does not overlap with existing networks

### 4.3 Execute the Deployment

```bash
az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters "infra/parameters/$ENV.bicepparam" \
  --name "deploy-$ENV-manual" \
  --verbose
```

### 4.4 Verify Deployment

```bash
# Check deployment status
az deployment sub show \
  --name "deploy-$ENV-manual" \
  --query '{state: properties.provisioningState, timestamp: properties.timestamp}' \
  -o table

# List created resource groups
az group list \
  --query "[?tags.environment=='$ENV'].[name, location]" \
  -o table
```

---

## Step 5: Post-Deployment Configuration

### 5.1 Configure VNet Peering to Hub

```bash
# This should be handled by Bicep, but verify:
az network vnet peering list \
  --resource-group "rg-networking-$ENV-eus2" \
  --vnet-name "vnet-spoke-$ENV-eus2" \
  -o table
```

### 5.2 Enable pgvector Extension

```bash
PSQL_SERVER="psql-vector-$ENV-eus2"
PSQL_RG="rg-data-$ENV-eus2"

# Enable pgvector extension
az postgres flexible-server parameter set \
  --resource-group "$PSQL_RG" \
  --server-name "$PSQL_SERVER" \
  --name azure.extensions \
  --value "vector,pg_trgm,btree_gin"

# Restart the server to apply
az postgres flexible-server restart \
  --resource-group "$PSQL_RG" \
  --name "$PSQL_SERVER"

# Connect and create the extension
psql "host=$PSQL_SERVER.postgres.database.azure.com \
  dbname=postgres \
  user=<admin-user> \
  sslmode=require" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 5.3 Configure Microsoft Fabric Workspace

1. Log into the Fabric portal (https://app.fabric.microsoft.com)
2. Create a workspace following naming convention: `ws-lakehouse-<env>`
3. Assign the workspace to the Fabric capacity: `fc-dp-<env>-eus2`
4. Create Lakehouses: `lh-bronze-<env>`, `lh-silver-<env>`, `lh-gold-<env>`
5. Configure workspace access for the CI/CD service principal

### 5.4 Configure Microsoft Purview

> See `documentation/runbooks/purview-governance.md` for the full governance runbook.

#### 5.4.1 Run Governance Scripts (Automated)

```bash
cd scripts/governance
pip install -r requirements.txt

# Register data sources and configure scans
python register_sources.py

# Configure scans and trigger initial scan
python configure_scans.py --run-now

# Create business glossary (4 categories, 20 terms)
python create_glossary.py

# Create custom classification rules (5 custom + 7 built-in SITs)
python create_classifications.py

# Verify all governance configuration
python verify_governance.py
```

#### 5.4.2 Configure Sensitivity Labels (Manual)

1. Navigate to `compliance.microsoft.com` > Information Protection > Labels
2. Create labels: Public, General, Confidential, Highly Confidential, Restricted
3. Publish label policy targeting all users
4. See `documentation/runbooks/purview-governance.md` Section 3 for details

#### 5.4.3 Configure DLP Policies (Manual)

1. Navigate to `compliance.microsoft.com` > Data Loss Prevention > Policies
2. Create policies: Block PII Export, Alert Financial Data Share, Enforce Encryption
3. Start in Test mode for 2 weeks before enforcement
4. See `documentation/runbooks/purview-governance.md` Section 4 for details

#### 5.4.4 Verification Checklist

- [ ] ADLS Gen2 registered as data source in Purview
- [ ] Initial scan completed successfully
- [ ] Weekly scan schedule configured (Sunday 2 AM UTC)
- [ ] Business glossary created with 20 terms across 4 categories
- [ ] Custom classification rules (5) created and enabled
- [ ] Built-in SITs (7) enabled in scan rule set
- [ ] Sensitivity labels created and published (manual)
- [ ] DLP policies in test mode (manual)

### 5.5 Configure AI Foundry

1. Open AI Foundry portal
2. Create a project: `aip-rag-<env>`
3. Deploy models:
   - `text-embedding-3-small` for embeddings
   - `gpt-4o` for chat completions
4. Note the endpoint URLs and add them to Key Vault

### 5.6 Store Secrets in Key Vault

```bash
KV_NAME="kvdp${ENV}eus2001"

# Store PostgreSQL connection string
az keyvault secret set \
  --vault-name "$KV_NAME" \
  --name "postgresql-connection-string" \
  --value "<connection-string>"

# Store AI Foundry endpoint
az keyvault secret set \
  --vault-name "$KV_NAME" \
  --name "ai-foundry-endpoint" \
  --value "<endpoint-url>"

# Store AI Foundry API key (if not using managed identity)
az keyvault secret set \
  --vault-name "$KV_NAME" \
  --name "ai-foundry-api-key" \
  --value "<api-key>"
```

---

## Step 6: Validation Checklist

Run through this checklist to confirm the environment is operational:

### Infrastructure

- [ ] All resource groups created with correct tags
- [ ] VNet deployed with correct address space
- [ ] VNet peered to Hub VNet
- [ ] NSGs applied to all subnets
- [ ] Private Endpoints created and DNS resolving correctly
- [ ] Key Vault accessible from the VNet

### Data Services

- [ ] PostgreSQL Flexible Server running and accessible
- [ ] pgvector extension enabled
- [ ] Fabric capacity provisioned and active
- [ ] Fabric workspace created with Lakehouses
- [ ] Purview account accessible and data sources registered

### AI Services

- [ ] AI Foundry hub and project created
- [ ] Embedding model deployed and responding
- [ ] Chat model deployed and responding
- [ ] Models accessible via managed identity

### Applications

- [ ] App Service Plan provisioned
- [ ] Streamlit App Service created (placeholder deployment OK)
- [ ] React App Service created (placeholder deployment OK)
- [ ] Health check endpoints responding

### Security

- [ ] Managed identities created and assigned
- [ ] Key Vault secrets populated
- [ ] No public endpoints (Prod only)
- [ ] Diagnostic settings forwarding to Log Analytics

### CI/CD

- [ ] GitHub environment created with secrets
- [ ] OIDC authentication working (run a test workflow)
- [ ] Environment protection rules configured (Prod)

---

## Troubleshooting

### OIDC Authentication Fails

```
Error: AADSTS70021: No matching federated identity record found
```

**Cause:** The federated credential subject does not match the GitHub Actions token.

**Fix:** Verify the subject claim matches exactly:
```bash
az ad app federated-credential list --id "$APP_ID" -o table
```

Ensure the subject format is: `repo:vamshi455/AzureAI:environment:<env>`

### Resource Provider Not Registered

```
Error: The subscription is not registered to use namespace 'Microsoft.Fabric'
```

**Fix:** Re-run the provider registration from Step 1.1 and wait for completion:
```bash
az provider register --namespace "Microsoft.Fabric" --wait
az provider show --namespace "Microsoft.Fabric" --query "registrationState"
```

### VNet Peering Fails

```
Error: Virtual network peering cannot be created because the address spaces overlap
```

**Fix:** Check the VNet address spaces:
```bash
az network vnet list --query "[].{name:name, addressSpace:addressSpace.addressPrefixes}" -o table
```

Ensure no CIDR overlap between hub and spoke VNets. Refer to the network topology in
`documentation/architecture/platform-overview.md`.

### Bicep Deployment Fails with Validation Error

```bash
# Get detailed error information
az deployment sub show \
  --name "<deployment-name>" \
  --query "properties.error" \
  -o json
```

Common causes:
- Resource name conflicts (name already taken globally)
- SKU not available in the target region
- Quota exceeded on the subscription
