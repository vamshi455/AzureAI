#!/usr/bin/env bash
#
# init_environment.sh
# Sets up the local development environment for the Azure Data Platform.
#
# Usage:
#   chmod +x scripts/setup/init_environment.sh
#   ./scripts/setup/init_environment.sh
#
# What this script does:
#   1. Checks for required tools (Python, Node.js, Docker, Azure CLI, etc.)
#   2. Validates Azure CLI login status
#   3. Creates .env files for each application from templates
#   4. Installs Python dependencies for admin-portal and API
#   5. Installs Node.js dependencies for web-app
#   6. Validates the environment is ready for development
#

set -euo pipefail

# --- Colors and formatting ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# --- Project root directory ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# --- Logging helpers ---
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
header() { echo -e "\n${BOLD}${CYAN}=== $1 ===${NC}\n"; }

# --- Track failures ---
ERRORS=0
WARNINGS=0

check_command() {
    local cmd="$1"
    local min_version="${2:-}"
    local install_hint="${3:-}"

    if command -v "$cmd" &>/dev/null; then
        local version
        version=$("$cmd" --version 2>&1 | head -1 || echo "unknown")
        success "$cmd found: $version"
        return 0
    else
        error "$cmd not found."
        if [[ -n "$install_hint" ]]; then
            echo -e "       Install: ${CYAN}${install_hint}${NC}"
        fi
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

# ---------------------------------------------------------------
# Step 1: Check required tools
# ---------------------------------------------------------------
header "Checking Required Tools"

check_command "python3" "3.11" "https://www.python.org/downloads/ or brew install python@3.11"

# Check Python version is >= 3.11
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        success "Python version $PYTHON_VERSION >= 3.11"
    else
        warn "Python version $PYTHON_VERSION < 3.11. Some features may not work."
        WARNINGS=$((WARNINGS + 1))
    fi
fi

check_command "pip3" "" "Should come with Python 3"
check_command "node" "20" "https://nodejs.org/ or brew install node@20"

# Check Node.js version is >= 20
if command -v node &>/dev/null; then
    NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)
    if [[ "$NODE_MAJOR" -ge 20 ]]; then
        success "Node.js version >= 20"
    else
        warn "Node.js version $(node -v) < v20. Please upgrade."
        WARNINGS=$((WARNINGS + 1))
    fi
fi

check_command "npm" "" "Should come with Node.js"
check_command "docker" "" "https://docs.docker.com/get-docker/"
check_command "az" "" "https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
check_command "git" "" "https://git-scm.com/downloads"

# Optional tools
echo ""
info "Checking optional tools..."
check_command "jq" "" "brew install jq (optional, used for JSON processing)" || true
check_command "gh" "" "brew install gh (optional, GitHub CLI)" || true

# ---------------------------------------------------------------
# Step 2: Validate Azure CLI login
# ---------------------------------------------------------------
header "Validating Azure CLI Login"

if command -v az &>/dev/null; then
    if az account show &>/dev/null 2>&1; then
        AZURE_ACCOUNT=$(az account show --query "{name:name, id:id, tenantId:tenantId}" -o json 2>/dev/null)
        SUBSCRIPTION_NAME=$(echo "$AZURE_ACCOUNT" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])" 2>/dev/null || echo "unknown")
        SUBSCRIPTION_ID=$(echo "$AZURE_ACCOUNT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "unknown")
        TENANT_ID=$(echo "$AZURE_ACCOUNT" | python3 -c "import sys,json; print(json.load(sys.stdin)['tenantId'])" 2>/dev/null || echo "unknown")
        success "Azure CLI logged in"
        info "  Subscription: $SUBSCRIPTION_NAME"
        info "  Subscription ID: $SUBSCRIPTION_ID"
        info "  Tenant ID: $TENANT_ID"
    else
        warn "Azure CLI not logged in. Run: az login"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    error "Azure CLI not installed. Cannot validate login."
fi

# ---------------------------------------------------------------
# Step 3: Create .env files from templates
# ---------------------------------------------------------------
header "Creating Environment Files"

create_env_file() {
    local app_dir="$1"
    local app_name="$2"
    local env_content="$3"
    local env_file="${app_dir}/.env"

    if [[ -f "$env_file" ]]; then
        info "$app_name .env already exists, skipping. (Delete to regenerate.)"
    else
        echo "$env_content" > "$env_file"
        success "Created $app_name .env at ${env_file}"
    fi
}

# Admin Portal .env
create_env_file "${PROJECT_ROOT}/apps/admin-portal" "Admin Portal" \
'# Azure Data Platform - Admin Portal Configuration
# Copy this file and fill in your values

# Azure Identity
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=

# Azure Key Vault
KEY_VAULT_URL=https://kv-dataplatform-dev.vault.azure.net/

# Microsoft Fabric
FABRIC_API_BASE=https://api.fabric.microsoft.com/v1

# AI Foundry
AI_FOUNDRY_ENDPOINT=https://ai-foundry-eastus.openai.azure.com/
AI_FOUNDRY_API_KEY=
AI_FOUNDRY_API_VERSION=2024-12-01-preview

# PostgreSQL
POSTGRES_HOST=psql-dataplatform-dev.postgres.database.azure.com
POSTGRES_PORT=5432
POSTGRES_DB=dataplatform
POSTGRES_USER=
POSTGRES_PASSWORD=

# Streamlit
STREAMLIT_SERVER_PORT=8501
'

# Web App .env
create_env_file "${PROJECT_ROOT}/apps/web-app" "Web App" \
'# Azure Data Platform - Web App Configuration

# API Backend
VITE_API_BASE_URL=http://localhost:8000

# Azure AD / MSAL
VITE_AZURE_CLIENT_ID=
VITE_AZURE_TENANT_ID=
VITE_REDIRECT_URI=http://localhost:5173
VITE_API_SCOPE=api://data-platform-api/.default
'

# API Backend .env
create_env_file "${PROJECT_ROOT}/apps/api" "API Backend" \
'# Azure Data Platform - API Backend Configuration

# Server
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8501

# Azure Identity
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=

# Azure Key Vault
KEY_VAULT_URL=https://kv-dataplatform-dev.vault.azure.net/

# AI Foundry (Azure OpenAI)
AI_FOUNDRY_ENDPOINT=https://ai-foundry-eastus.openai.azure.com/
AI_FOUNDRY_API_KEY=
AI_FOUNDRY_API_VERSION=2024-12-01-preview

# PostgreSQL
POSTGRES_HOST=psql-dataplatform-dev.postgres.database.azure.com
POSTGRES_PORT=5432
POSTGRES_DB=dataplatform
POSTGRES_USER=
POSTGRES_PASSWORD=

# Slack Integration
SLACK_WEBHOOK_URL=
SLACK_BOT_TOKEN=
SLACK_DEFAULT_CHANNEL=#data-platform-alerts

# Plane (Ticketing)
PLANE_API_BASE=https://plane.company.com/api/v1
PLANE_API_KEY=
PLANE_WORKSPACE_SLUG=data-platform
PLANE_PROJECT_ID=
'

# ---------------------------------------------------------------
# Step 4: Install Python dependencies
# ---------------------------------------------------------------
header "Installing Python Dependencies"

install_python_deps() {
    local app_dir="$1"
    local app_name="$2"
    local req_file="${app_dir}/requirements.txt"

    if [[ ! -f "$req_file" ]]; then
        warn "$app_name requirements.txt not found at $req_file"
        return
    fi

    info "Installing $app_name dependencies..."

    # Create virtual environment if it doesn't exist
    local venv_dir="${app_dir}/.venv"
    if [[ ! -d "$venv_dir" ]]; then
        python3 -m venv "$venv_dir"
        success "Created virtual environment at $venv_dir"
    fi

    # Install dependencies
    if "${venv_dir}/bin/pip" install -r "$req_file" -q 2>/dev/null; then
        success "$app_name dependencies installed"
    else
        error "Failed to install $app_name dependencies"
        ERRORS=$((ERRORS + 1))
    fi
}

install_python_deps "${PROJECT_ROOT}/apps/admin-portal" "Admin Portal"
install_python_deps "${PROJECT_ROOT}/apps/api" "API Backend"

# ---------------------------------------------------------------
# Step 5: Install Node.js dependencies
# ---------------------------------------------------------------
header "Installing Node.js Dependencies"

WEB_APP_DIR="${PROJECT_ROOT}/apps/web-app"

if [[ -f "${WEB_APP_DIR}/package.json" ]]; then
    info "Installing Web App dependencies..."
    if (cd "$WEB_APP_DIR" && npm install --silent 2>/dev/null); then
        success "Web App dependencies installed"
    else
        warn "npm install had issues. You may need to run it manually."
        WARNINGS=$((WARNINGS + 1))
    fi
else
    warn "Web App package.json not found"
fi

# ---------------------------------------------------------------
# Step 6: Create config directory and default pipeline config
# ---------------------------------------------------------------
header "Setting Up Configuration"

CONFIG_DIR="${PROJECT_ROOT}/apps/admin-portal/config"
if [[ ! -d "$CONFIG_DIR" ]]; then
    mkdir -p "$CONFIG_DIR"
    success "Created config directory at $CONFIG_DIR"
fi

# ---------------------------------------------------------------
# Step 7: Validate Docker
# ---------------------------------------------------------------
header "Validating Docker"

if command -v docker &>/dev/null; then
    if docker info &>/dev/null 2>&1; then
        success "Docker daemon is running"
        DOCKER_VERSION=$(docker --version)
        info "  $DOCKER_VERSION"
    else
        warn "Docker is installed but the daemon is not running."
        warn "Start Docker Desktop or the Docker daemon to use containers."
        WARNINGS=$((WARNINGS + 1))
    fi
fi

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
header "Setup Summary"

echo -e "${BOLD}Project Root:${NC} ${PROJECT_ROOT}"
echo ""
echo -e "${BOLD}Applications:${NC}"
echo "  Admin Portal:  ${PROJECT_ROOT}/apps/admin-portal/"
echo "  Web App:       ${PROJECT_ROOT}/apps/web-app/"
echo "  API Backend:   ${PROJECT_ROOT}/apps/api/"
echo ""

if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}Environment setup completed successfully!${NC}"
elif [[ $ERRORS -eq 0 ]]; then
    echo -e "${YELLOW}${BOLD}Environment setup completed with $WARNINGS warning(s).${NC}"
else
    echo -e "${RED}${BOLD}Environment setup completed with $ERRORS error(s) and $WARNINGS warning(s).${NC}"
    echo -e "${RED}Please resolve the errors above before proceeding.${NC}"
fi

echo ""
echo -e "${BOLD}Quick Start:${NC}"
echo ""
echo "  # Start Admin Portal"
echo "  cd ${PROJECT_ROOT}/apps/admin-portal"
echo "  source .venv/bin/activate"
echo "  streamlit run app.py"
echo ""
echo "  # Start API Backend"
echo "  cd ${PROJECT_ROOT}/apps/api"
echo "  source .venv/bin/activate"
echo "  uvicorn src.main:app --reload --port 8000"
echo ""
echo "  # Start Web App"
echo "  cd ${PROJECT_ROOT}/apps/web-app"
echo "  npm run dev"
echo ""
echo -e "${BOLD}Next Steps:${NC}"
echo "  1. Fill in the .env files with your Azure credentials"
echo "  2. Run 'az login' if not already logged in"
echo "  3. Start the services using the commands above"
echo ""
