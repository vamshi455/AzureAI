// ============================================================================
// Identity Module - Managed Identities and Role Assignments
// ============================================================================

@description('Azure region for resources.')
param location string

@description('Environment name.')
@allowed(['dev', 'qa', 'prod'])
param environment string

@description('Resource prefix for naming.')
@minLength(2)
@maxLength(5)
param resourcePrefix string

@description('Tags to apply to all resources.')
param tags object

// ============================================================================
// Variables
// ============================================================================

var platformIdentityName = '${resourcePrefix}-id-platform-${environment}'
var dataIngestionIdentityName = '${resourcePrefix}-id-data-ingestion-${environment}'
var appServiceIdentityName = '${resourcePrefix}-id-appsvc-${environment}'

// Built-in role definition IDs
var roleDefinitions = {
  contributor: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
  reader: 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  keyVaultSecretsOfficer: 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  cognitiveServicesContributor: '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}

// ============================================================================
// Platform Managed Identity
// ============================================================================

resource platformIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: platformIdentityName
  location: location
  tags: tags
}

// ============================================================================
// Data Ingestion Managed Identity
// ============================================================================

resource dataIngestionIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: dataIngestionIdentityName
  location: location
  tags: tags
}

// ============================================================================
// App Service Managed Identity
// ============================================================================

resource appServiceIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: appServiceIdentityName
  location: location
  tags: tags
}

// ============================================================================
// Role Assignments - Platform Identity
// ============================================================================

// Platform identity gets Key Vault Secrets Officer
resource platformKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, platformIdentity.id, roleDefinitions.keyVaultSecretsOfficer)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitions.keyVaultSecretsOfficer)
    principalId: platformIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Platform identity gets Monitoring Metrics Publisher
resource platformMonitoringRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, platformIdentity.id, roleDefinitions.monitoringMetricsPublisher)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitions.monitoringMetricsPublisher)
    principalId: platformIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Role Assignments - Data Ingestion Identity
// ============================================================================

// Data ingestion identity gets Storage Blob Data Contributor
resource dataIngestionStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, dataIngestionIdentity.id, roleDefinitions.storageBlobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitions.storageBlobDataContributor)
    principalId: dataIngestionIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Data ingestion identity gets Key Vault Secrets User
resource dataIngestionKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, dataIngestionIdentity.id, roleDefinitions.keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitions.keyVaultSecretsUser)
    principalId: dataIngestionIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Role Assignments - App Service Identity
// ============================================================================

// App service identity gets Key Vault Secrets User
resource appServiceKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, appServiceIdentity.id, roleDefinitions.keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitions.keyVaultSecretsUser)
    principalId: appServiceIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// App service identity gets Cognitive Services User (for AI Foundry)
resource appServiceCognitiveRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, appServiceIdentity.id, roleDefinitions.cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitions.cognitiveServicesUser)
    principalId: appServiceIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// App service identity gets Storage Blob Data Reader
resource appServiceStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, appServiceIdentity.id, roleDefinitions.storageBlobDataReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitions.storageBlobDataReader)
    principalId: appServiceIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Outputs
// ============================================================================

output platformIdentityId string = platformIdentity.id
output platformIdentityPrincipalId string = platformIdentity.properties.principalId
output platformIdentityClientId string = platformIdentity.properties.clientId
output platformIdentityName string = platformIdentity.name

output dataIngestionIdentityId string = dataIngestionIdentity.id
output dataIngestionIdentityPrincipalId string = dataIngestionIdentity.properties.principalId
output dataIngestionIdentityClientId string = dataIngestionIdentity.properties.clientId

output appServiceIdentityId string = appServiceIdentity.id
output appServiceIdentityPrincipalId string = appServiceIdentity.properties.principalId
output appServiceIdentityClientId string = appServiceIdentity.properties.clientId
