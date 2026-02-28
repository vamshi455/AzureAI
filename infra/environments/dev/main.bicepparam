using '../../main.bicep'

// ============================================================================
// Dev Environment Parameters
// Subscription: Sub-DataPlatform-NonProd
// ============================================================================

param environment = 'dev'
param location = 'eastus2'
param resourcePrefix = 'dp'
param resourceGroupName = 'dp-rg-dev'

// --- Tags ---
param ownerTag = 'DataPlatformTeam'
param costCenterTag = 'CC-DEV-1001'
param dataClassificationTag = 'Internal'

// --- Networking ---
param hubVnetAddressSpace = '10.0.0.0/16'
param spokeVnetAddressSpace = '10.1.0.0/16'

// --- PostgreSQL ---
param postgresAdminLogin = readEnvironmentVariable('POSTGRES_ADMIN_LOGIN', '')
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD', '')
param postgresSkuName = 'Standard_B2s'
param postgresStorageSizeGB = 64

// --- Key Vault ---
param keyVaultAdminObjectId = readEnvironmentVariable('KEYVAULT_ADMIN_OBJECT_ID', '')

// --- App Service ---
param appServicePlanSku = 'B2'

// --- Fabric ---
param enableFabric = true
param fabricSku = 'F2'
param fabricAdminMembers = []

// --- Purview ---
param enablePurview = true

// --- AI Foundry ---
param enableAIFoundry = true

// --- Storage (Lakehouse) ---
param enableStorage = true

// --- Plane (Ticketing) ---
param enablePlane = false
param planeImageTag = 'latest'
