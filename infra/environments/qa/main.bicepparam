using '../../main.bicep'

// ============================================================================
// QA Environment Parameters
// Subscription: Sub-DataPlatform-NonProd
// ============================================================================

param environment = 'qa'
param location = 'eastus2'
param resourcePrefix = 'dp'
param resourceGroupName = 'dp-rg-qa'

// --- Tags ---
param ownerTag = 'DataPlatformTeam'
param costCenterTag = 'CC-QA-1002'
param dataClassificationTag = 'Confidential'

// --- Networking ---
param hubVnetAddressSpace = '10.2.0.0/16'
param spokeVnetAddressSpace = '10.3.0.0/16'

// --- PostgreSQL ---
param postgresAdminLogin = readEnvironmentVariable('POSTGRES_ADMIN_LOGIN', '')
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD', '')
param postgresSkuName = 'Standard_D2s_v3'
param postgresStorageSizeGB = 128

// --- Key Vault ---
param keyVaultAdminObjectId = readEnvironmentVariable('KEYVAULT_ADMIN_OBJECT_ID', '')

// --- App Service ---
param appServicePlanSku = 'S2'

// --- Fabric ---
param enableFabric = true
param fabricSku = 'F4'
param fabricAdminMembers = []

// --- Purview ---
param enablePurview = true

// --- AI Foundry ---
param enableAIFoundry = true

// --- Plane (Ticketing) ---
param enablePlane = true
param planeImageTag = 'stable'
