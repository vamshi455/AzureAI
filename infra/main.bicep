// ============================================================================
// Manufacturing + Sales Data Platform - Main Orchestrator
// ============================================================================
// Deploys all platform modules based on environment configuration.
// Usage:
//   az deployment sub create \
//     --location eastus2 \
//     --template-file infra/main.bicep \
//     --parameters infra/environments/dev/main.bicepparam
// ============================================================================

targetScope = 'subscription'

// ============================================================================
// Parameters
// ============================================================================

@description('Environment name for the deployment.')
@allowed(['dev', 'qa', 'prod'])
param environment string

@description('Azure region for all resources.')
@allowed(['eastus2', 'eastus', 'westus2', 'centralus'])
param location string = 'eastus2'

@description('Resource prefix used in naming convention.')
@minLength(2)
@maxLength(5)
param resourcePrefix string = 'dp'

@description('Name of the resource group.')
@minLength(3)
@maxLength(64)
param resourceGroupName string = '${resourcePrefix}-rg-${environment}'

@description('Owner tag for all resources.')
param ownerTag string

@description('Cost center for billing attribution.')
param costCenterTag string

@description('Data classification level.')
@allowed(['Public', 'Internal', 'Confidential', 'Highly Confidential'])
param dataClassificationTag string = 'Confidential'

// --- Networking Parameters ---
@description('Address space for the hub VNet.')
param hubVnetAddressSpace string = '10.0.0.0/16'

@description('Address space for the spoke VNet.')
param spokeVnetAddressSpace string = '10.1.0.0/16'

// --- PostgreSQL Parameters ---
@description('PostgreSQL administrator login.')
@minLength(3)
@maxLength(63)
@secure()
param postgresAdminLogin string

@description('PostgreSQL administrator password.')
@secure()
@minLength(8)
param postgresAdminPassword string

@description('PostgreSQL SKU name.')
@allowed(['Standard_B1ms', 'Standard_B2s', 'Standard_D2s_v3', 'Standard_D4s_v3', 'Standard_D8s_v3'])
param postgresSkuName string = 'Standard_B2s'

@description('PostgreSQL storage size in GB.')
@allowed([32, 64, 128, 256, 512, 1024])
param postgresStorageSizeGB int = 64

// --- Key Vault Parameters ---
@description('Object ID of the Key Vault admin (AAD user or group).')
param keyVaultAdminObjectId string

// --- App Service Parameters ---
@description('App Service Plan SKU.')
@allowed(['B1', 'B2', 'B3', 'S1', 'S2', 'S3', 'P1v3', 'P2v3', 'P3v3'])
param appServicePlanSku string = 'B2'

// --- Fabric Parameters ---
@description('Enable Microsoft Fabric capacity deployment.')
param enableFabric bool = true

@description('Fabric capacity SKU.')
@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64', 'F128', 'F256', 'F512', 'F1024'])
param fabricSku string = 'F2'

@description('Fabric capacity admin members (AAD object IDs or UPNs).')
param fabricAdminMembers array = []

// --- Purview Parameters ---
@description('Enable Microsoft Purview deployment.')
param enablePurview bool = true

// --- AI Foundry Parameters ---
@description('Enable AI Foundry deployment.')
param enableAIFoundry bool = true

// --- Plane (Ticketing) Parameters ---
@description('Enable Plane ticketing system deployment.')
param enablePlane bool = false

@description('Plane container image tag.')
param planeImageTag string = 'latest'

// ============================================================================
// Variables
// ============================================================================

var tags = {
  Environment: environment
  CostCenter: costCenterTag
  DataClassification: dataClassificationTag
  Owner: ownerTag
  ManagedBy: 'Bicep'
  Project: 'ManufacturingSalesDataPlatform'
}

var isProd = environment == 'prod'

// ============================================================================
// Resource Group
// ============================================================================

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// ============================================================================
// Module Deployments
// ============================================================================

// --- Monitoring (deployed first - other modules reference Log Analytics) ---
module monitoring 'modules/monitoring/main.bicep' = {
  scope: rg
  name: 'monitoring-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    retentionInDays: isProd ? 90 : 30
  }
}

// --- Networking ---
module networking 'modules/networking/main.bicep' = {
  scope: rg
  name: 'networking-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    hubVnetAddressSpace: hubVnetAddressSpace
    spokeVnetAddressSpace: spokeVnetAddressSpace
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
  }
}

// --- Identity ---
module identity 'modules/identity/main.bicep' = {
  scope: rg
  name: 'identity-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
  }
}

// --- Key Vault ---
module keyvault 'modules/keyvault/main.bicep' = {
  scope: rg
  name: 'keyvault-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    adminObjectId: keyVaultAdminObjectId
    platformIdentityPrincipalId: identity.outputs.platformIdentityPrincipalId
    privateEndpointSubnetId: networking.outputs.privateEndpointSubnetId
    vnetId: networking.outputs.spokeVnetId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    enablePurgeProtection: isProd
  }
}

// --- PostgreSQL ---
module postgresql 'modules/postgresql/main.bicep' = {
  scope: rg
  name: 'postgresql-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    administratorLogin: postgresAdminLogin
    administratorPassword: postgresAdminPassword
    skuName: postgresSkuName
    storageSizeGB: postgresStorageSizeGB
    dataSubnetId: networking.outputs.dataSubnetId
    privateDnsZoneId: networking.outputs.postgresPrivateDnsZoneId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    highAvailabilityEnabled: isProd
    backupRetentionDays: isProd ? 35 : 7
    geoRedundantBackup: isProd
  }
}

// --- AI Foundry ---
module aiFoundry 'modules/ai-foundry/main.bicep' = if (enableAIFoundry) {
  scope: rg
  name: 'ai-foundry-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    privateEndpointSubnetId: networking.outputs.privateEndpointSubnetId
    vnetId: networking.outputs.spokeVnetId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    keyVaultId: keyvault.outputs.keyVaultId
    applicationInsightsId: monitoring.outputs.applicationInsightsId
    platformIdentityId: identity.outputs.platformIdentityId
  }
}

// --- App Service ---
module appService 'modules/app-service/main.bicep' = {
  scope: rg
  name: 'app-service-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    appServicePlanSku: appServicePlanSku
    appServiceSubnetId: networking.outputs.appServiceSubnetId
    privateEndpointSubnetId: networking.outputs.privateEndpointSubnetId
    vnetId: networking.outputs.spokeVnetId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    platformIdentityId: identity.outputs.platformIdentityId
    keyVaultUri: keyvault.outputs.keyVaultUri
    postgresqlFqdn: postgresql.outputs.fqdn
  }
}

// --- Fabric ---
module fabric 'modules/fabric/main.bicep' = if (enableFabric) {
  scope: rg
  name: 'fabric-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    skuName: fabricSku
    adminMembers: fabricAdminMembers
  }
}

// --- Purview ---
module purview 'modules/purview/main.bicep' = if (enablePurview) {
  scope: rg
  name: 'purview-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    privateEndpointSubnetId: networking.outputs.privateEndpointSubnetId
    vnetId: networking.outputs.spokeVnetId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    platformIdentityPrincipalId: identity.outputs.platformIdentityPrincipalId
  }
}

// --- Plane (Ticketing) ---
module plane 'modules/plane/main.bicep' = if (enablePlane) {
  scope: rg
  name: 'plane-${environment}'
  params: {
    location: location
    environment: environment
    resourcePrefix: resourcePrefix
    tags: tags
    imageTag: planeImageTag
    appSubnetId: networking.outputs.appServiceSubnetId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
  }
}

// ============================================================================
// Outputs
// ============================================================================

output resourceGroupName string = rg.name
output logAnalyticsWorkspaceId string = monitoring.outputs.logAnalyticsWorkspaceId
output spokeVnetId string = networking.outputs.spokeVnetId
output keyVaultUri string = keyvault.outputs.keyVaultUri
output postgresqlFqdn string = postgresql.outputs.fqdn
output platformIdentityId string = identity.outputs.platformIdentityId
output platformIdentityClientId string = identity.outputs.platformIdentityClientId
