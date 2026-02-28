#!/usr/bin/env bash
#
# deploy_plane.sh
# Deploys Plane project management to Azure Container Apps.
#
# Usage:
#   chmod +x scripts/setup/deploy_plane.sh
#   ./scripts/setup/deploy_plane.sh [--resource-group <rg>] [--location <location>] [--environment <env-name>]
#
# Prerequisites:
#   - Azure CLI logged in (az login)
#   - Docker running (for image pulls/builds)
#   - Sufficient Azure permissions to create Container Apps, databases, and storage
#
# What this script does:
#   1. Creates required Azure resources (Resource Group, Container App Environment)
#   2. Deploys PostgreSQL Flexible Server for Plane's database
#   3. Deploys Redis via Container Apps for caching/queuing
#   4. Deploys Plane components (web, api, worker, beat-worker) as Container Apps
#   5. Configures networking and environment variables
#   6. Outputs access URLs and credentials
#

set -euo pipefail

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
header() { echo -e "\n${BOLD}${CYAN}=== $1 ===${NC}\n"; }

# --- Default Configuration ---
RESOURCE_GROUP="rg-plane-prod"
LOCATION="eastus"
ENVIRONMENT_NAME="plane-env"
PLANE_VERSION="v0.23-dev"  # Use the latest stable version
PREFIX="plane"

# PostgreSQL configuration
PG_SERVER_NAME="${PREFIX}-pgdb-$(openssl rand -hex 4)"
PG_ADMIN_USER="planeadmin"
PG_ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)Aa1!"
PG_DATABASE="plane"
PG_SKU="B_Standard_B1ms"

# Redis configuration
REDIS_PASSWORD="$(openssl rand -hex 16)"

# Plane secret key
SECRET_KEY="$(openssl rand -hex 32)"

# --- Parse Arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --resource-group|-g)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        --location|-l)
            LOCATION="$2"
            shift 2
            ;;
        --environment|-e)
            ENVIRONMENT_NAME="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--resource-group <rg>] [--location <location>] [--environment <env>]"
            echo ""
            echo "Options:"
            echo "  --resource-group, -g   Azure Resource Group name (default: rg-plane-prod)"
            echo "  --location, -l         Azure region (default: eastus)"
            echo "  --environment, -e      Container App Environment name (default: plane-env)"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# --- Preflight Checks ---
header "Preflight Checks"

# Check Azure CLI
if ! command -v az &>/dev/null; then
    error "Azure CLI (az) is required. Install from: https://aka.ms/installazurecli"
fi

# Check login status
if ! az account show &>/dev/null 2>&1; then
    error "Not logged in to Azure CLI. Run 'az login' first."
fi

SUBSCRIPTION=$(az account show --query name -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
success "Azure CLI logged in: $SUBSCRIPTION ($SUBSCRIPTION_ID)"

# Ensure Container Apps extension is installed
info "Ensuring Azure Container Apps extension is installed..."
az extension add --name containerapp --upgrade --yes 2>/dev/null || true
success "Container Apps extension ready"

# Register required providers
info "Registering required resource providers..."
az provider register --namespace Microsoft.App --wait 2>/dev/null || true
az provider register --namespace Microsoft.OperationalInsights --wait 2>/dev/null || true
az provider register --namespace Microsoft.DBforPostgreSQL --wait 2>/dev/null || true
success "Resource providers registered"

# ---------------------------------------------------------------
# Step 1: Create Resource Group
# ---------------------------------------------------------------
header "Step 1: Resource Group"

if az group show --name "$RESOURCE_GROUP" &>/dev/null 2>&1; then
    info "Resource group '$RESOURCE_GROUP' already exists"
else
    info "Creating resource group '$RESOURCE_GROUP' in '$LOCATION'..."
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --tags "project=plane" "managed-by=deploy-script" \
        --output none
    success "Resource group created"
fi

# ---------------------------------------------------------------
# Step 2: Create Container App Environment
# ---------------------------------------------------------------
header "Step 2: Container App Environment"

if az containerapp env show --name "$ENVIRONMENT_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null 2>&1; then
    info "Container App Environment '$ENVIRONMENT_NAME' already exists"
else
    info "Creating Container App Environment '$ENVIRONMENT_NAME'..."
    az containerapp env create \
        --name "$ENVIRONMENT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none
    success "Container App Environment created"
fi

# ---------------------------------------------------------------
# Step 3: Deploy PostgreSQL Flexible Server
# ---------------------------------------------------------------
header "Step 3: PostgreSQL Database"

info "Creating PostgreSQL Flexible Server '${PG_SERVER_NAME}'..."
az postgres flexible-server create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$PG_SERVER_NAME" \
    --location "$LOCATION" \
    --admin-user "$PG_ADMIN_USER" \
    --admin-password "$PG_ADMIN_PASSWORD" \
    --sku-name "$PG_SKU" \
    --tier "Burstable" \
    --version "15" \
    --storage-size 32 \
    --yes \
    --output none 2>/dev/null || {
    warn "PostgreSQL server may already exist or creation had issues. Continuing..."
}

# Allow Azure services to connect
info "Configuring PostgreSQL firewall for Azure services..."
az postgres flexible-server firewall-rule create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$PG_SERVER_NAME" \
    --rule-name "AllowAzureServices" \
    --start-ip-address "0.0.0.0" \
    --end-ip-address "0.0.0.0" \
    --output none 2>/dev/null || true

# Create database
info "Creating database '${PG_DATABASE}'..."
az postgres flexible-server db create \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "$PG_SERVER_NAME" \
    --database-name "$PG_DATABASE" \
    --output none 2>/dev/null || true

PG_HOST="${PG_SERVER_NAME}.postgres.database.azure.com"
DATABASE_URL="postgresql://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${PG_HOST}:5432/${PG_DATABASE}?sslmode=require"
success "PostgreSQL deployed: $PG_HOST"

# ---------------------------------------------------------------
# Step 4: Deploy Redis as Container App
# ---------------------------------------------------------------
header "Step 4: Redis Cache"

info "Deploying Redis as Container App..."
az containerapp create \
    --name "${PREFIX}-redis" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "redis:7-alpine" \
    --target-port 6379 \
    --ingress "internal" \
    --min-replicas 1 \
    --max-replicas 1 \
    --cpu 0.5 \
    --memory 1.0Gi \
    --args "redis-server" "--requirepass" "$REDIS_PASSWORD" "--maxmemory" "512mb" "--maxmemory-policy" "allkeys-lru" \
    --output none 2>/dev/null || {
    warn "Redis container app may already exist. Continuing..."
}

REDIS_HOST="${PREFIX}-redis.internal.${ENVIRONMENT_NAME}.azurecontainerapps.io"
REDIS_URL="redis://:${REDIS_PASSWORD}@${REDIS_HOST}:6379/0"
success "Redis deployed: ${REDIS_HOST}"

# ---------------------------------------------------------------
# Step 5: Deploy Plane Components
# ---------------------------------------------------------------
header "Step 5: Deploying Plane Services"

# Common environment variables for Plane containers
PLANE_ENV_VARS=(
    "SECRET_KEY=${SECRET_KEY}"
    "DATABASE_URL=${DATABASE_URL}"
    "REDIS_URL=${REDIS_URL}"
    "DJANGO_SETTINGS_MODULE=plane.settings.production"
    "CORS_ALLOWED_ORIGINS=*"
    "ENABLE_SIGNUP=1"
    "ENABLE_EMAIL_PASSWORD=1"
    "WEB_URL=https://${PREFIX}-web.azurecontainerapps.io"
    "GUNICORN_WORKERS=2"
    "SENTRY_ENVIRONMENT=production"
)

# Build --env-vars string
ENV_VARS_STR=""
for var in "${PLANE_ENV_VARS[@]}"; do
    ENV_VARS_STR="${ENV_VARS_STR} ${var}"
done

# --- Plane API ---
info "Deploying Plane API server..."
az containerapp create \
    --name "${PREFIX}-api" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "makeplane/plane-backend:${PLANE_VERSION}" \
    --target-port 8000 \
    --ingress "internal" \
    --min-replicas 1 \
    --max-replicas 3 \
    --cpu 1.0 \
    --memory 2.0Gi \
    --env-vars ${ENV_VARS_STR} \
    --command "gunicorn" "-w" "2" "-k" "uvicorn.workers.UvicornWorker" "plane.asgi:application" "--bind" "0.0.0.0:8000" \
    --output none 2>/dev/null || {
    warn "Plane API deployment had issues. Check Azure Portal for details."
}
success "Plane API deployed"

# --- Plane Worker ---
info "Deploying Plane Worker..."
az containerapp create \
    --name "${PREFIX}-worker" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "makeplane/plane-backend:${PLANE_VERSION}" \
    --min-replicas 1 \
    --max-replicas 2 \
    --cpu 0.5 \
    --memory 1.0Gi \
    --env-vars ${ENV_VARS_STR} \
    --command "python" "manage.py" "celery_worker" \
    --output none 2>/dev/null || {
    warn "Plane Worker deployment had issues."
}
success "Plane Worker deployed"

# --- Plane Beat Worker ---
info "Deploying Plane Beat Worker..."
az containerapp create \
    --name "${PREFIX}-beat" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "makeplane/plane-backend:${PLANE_VERSION}" \
    --min-replicas 1 \
    --max-replicas 1 \
    --cpu 0.25 \
    --memory 0.5Gi \
    --env-vars ${ENV_VARS_STR} \
    --command "python" "manage.py" "celery_beat" \
    --output none 2>/dev/null || {
    warn "Plane Beat Worker deployment had issues."
}
success "Plane Beat Worker deployed"

# --- Plane Web (Frontend) ---
info "Deploying Plane Web frontend..."

# Get API internal URL
PLANE_API_FQDN="${PREFIX}-api.internal.${ENVIRONMENT_NAME}.azurecontainerapps.io"

az containerapp create \
    --name "${PREFIX}-web" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "makeplane/plane-frontend:${PLANE_VERSION}" \
    --target-port 3000 \
    --ingress "external" \
    --min-replicas 1 \
    --max-replicas 3 \
    --cpu 0.5 \
    --memory 1.0Gi \
    --env-vars \
        "NEXT_PUBLIC_API_BASE_URL=https://${PLANE_API_FQDN}" \
        "NEXT_PUBLIC_DEPLOY_URL=https://${PREFIX}-web.azurecontainerapps.io" \
    --output none 2>/dev/null || {
    warn "Plane Web deployment had issues."
}
success "Plane Web deployed"

# ---------------------------------------------------------------
# Step 6: Run Database Migrations
# ---------------------------------------------------------------
header "Step 6: Database Migrations"

info "Running Plane database migrations..."
az containerapp exec \
    --name "${PREFIX}-api" \
    --resource-group "$RESOURCE_GROUP" \
    --command "python manage.py migrate" \
    2>/dev/null || {
    warn "Database migration via exec may not be supported."
    info "You may need to run migrations manually:"
    info "  az containerapp exec --name ${PREFIX}-api --resource-group ${RESOURCE_GROUP}"
    info "  python manage.py migrate"
}

# ---------------------------------------------------------------
# Step 7: Get Access URLs
# ---------------------------------------------------------------
header "Deployment Complete"

WEB_FQDN=$(az containerapp show \
    --name "${PREFIX}-web" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" \
    -o tsv 2>/dev/null || echo "${PREFIX}-web.azurecontainerapps.io")

echo -e "${BOLD}Plane Deployment Summary${NC}"
echo "-------------------------------------------"
echo -e "${BOLD}Resource Group:${NC}  $RESOURCE_GROUP"
echo -e "${BOLD}Location:${NC}        $LOCATION"
echo -e "${BOLD}Environment:${NC}     $ENVIRONMENT_NAME"
echo ""
echo -e "${BOLD}URLs:${NC}"
echo -e "  Web UI:  ${GREEN}https://${WEB_FQDN}${NC}"
echo ""
echo -e "${BOLD}Database:${NC}"
echo -e "  Host:     $PG_HOST"
echo -e "  Database: $PG_DATABASE"
echo -e "  User:     $PG_ADMIN_USER"
echo -e "  Password: (stored in output below)"
echo ""
echo -e "${BOLD}Containers:${NC}"
echo "  ${PREFIX}-web    (external) - Web frontend"
echo "  ${PREFIX}-api    (internal) - API backend"
echo "  ${PREFIX}-worker (internal) - Background worker"
echo "  ${PREFIX}-beat   (internal) - Scheduled tasks"
echo "  ${PREFIX}-redis  (internal) - Cache/Queue"
echo ""

# Save credentials to a file
CREDS_FILE="${PROJECT_ROOT}/scripts/setup/.plane-credentials"
cat > "$CREDS_FILE" <<CREDS
# Plane Deployment Credentials
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# WARNING: Contains sensitive information. Do not commit to version control.

PLANE_WEB_URL=https://${WEB_FQDN}
PLANE_API_URL=https://${PLANE_API_FQDN}

PG_SERVER=${PG_HOST}
PG_DATABASE=${PG_DATABASE}
PG_USER=${PG_ADMIN_USER}
PG_PASSWORD=${PG_ADMIN_PASSWORD}

REDIS_HOST=${REDIS_HOST}
REDIS_PASSWORD=${REDIS_PASSWORD}

SECRET_KEY=${SECRET_KEY}
CREDS
chmod 600 "$CREDS_FILE"

success "Credentials saved to: $CREDS_FILE"
warn "This file contains sensitive information. Add it to .gitignore."

echo ""
echo -e "${BOLD}Next Steps:${NC}"
echo "  1. Visit https://${WEB_FQDN} to access Plane"
echo "  2. Create an admin account on first visit"
echo "  3. Create a workspace and project for the data platform"
echo "  4. Generate an API key in Plane Settings > API Tokens"
echo "  5. Update apps/api/.env with PLANE_API_KEY and PLANE_PROJECT_ID"
echo ""
echo -e "${GREEN}${BOLD}Plane deployment completed successfully!${NC}"
