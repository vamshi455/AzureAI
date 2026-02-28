using '../../main.bicep'

// ============================================================================
// Prod Environment Parameters
// Subscription: Sub-DataPlatform-Prod
// ============================================================================

param environment = 'prod'
param location = 'eastus2'
param resourcePrefix = 'dp'
param resourceGroupName = 'dp-rg-prod'

// --- Tags ---
param ownerTag = 'DataPlatformTeam'
param costCenterTag = 'CC-PROD-1003'
param dataClassificationTag = 'Highly Confidential'

// --- Networking ---
param hubVnetAddressSpace = '10.4.0.0/16'
param spokeVnetAddressSpace = '10.5.0.0/16'

// --- PostgreSQL ---
param postgresAdminLogin = readEnvironmentVariable('POSTGRES_ADMIN_LOGIN', '')
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD', '')
param postgresSkuName = 'Standard_D4s_v3'
param postgresStorageSizeGB = 512

// --- Key Vault ---
param keyVaultAdminObjectId = readEnvironmentVariable('KEYVAULT_ADMIN_OBJECT_ID', '')

// --- App Service ---
param appServicePlanSku = 'P2v3'

// --- Fabric ---
param enableFabric = true
param fabricSku = 'F64'
param fabricAdminMembers = []

// --- Purview ---
param enablePurview = true

// --- AI Foundry ---
param enableAIFoundry = true

// --- Plane (Ticketing) ---
param enablePlane = true
param planeImageTag = 'stable'
