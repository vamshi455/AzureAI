// ============================================================================
// AI Foundry Module - Azure AI Foundry Hub + Project
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

@description('Subnet ID for private endpoints.')
param privateEndpointSubnetId string

@description('Log Analytics Workspace ID for diagnostic settings.')
param logAnalyticsWorkspaceId string

@description('Key Vault resource ID for AI Foundry secrets.')
param keyVaultId string

@description('Application Insights resource ID.')
param applicationInsightsId string

@description('Platform managed identity resource ID.')
param platformIdentityId string

@description('Public network access setting. Use Enabled for initial dev setup.')
@allowed(['Enabled', 'Disabled'])
param publicNetworkAccess string = 'Disabled'

// ============================================================================
// Variables
// ============================================================================

var hubName = '${resourcePrefix}-aih-${environment}'
var projectName = '${resourcePrefix}-aip-mfg-sales-${environment}'
var storageAccountName = replace('${resourcePrefix}stai${environment}${uniqueString(resourceGroup().id)}', '-', '')
var truncatedStorageName = length(storageAccountName) > 24 ? substring(storageAccountName, 0, 24) : storageAccountName
var containerRegistryName = replace('${resourcePrefix}crai${environment}${uniqueString(resourceGroup().id)}', '-', '')
var truncatedCrName = length(containerRegistryName) > 50 ? substring(containerRegistryName, 0, 50) : containerRegistryName
var privateEndpointNameHub = '${resourcePrefix}-pe-aih-${environment}'

// ============================================================================
// Storage Account for AI Foundry
// ============================================================================

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: truncatedStorageName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
    encryption: {
      services: {
        blob: {
          enabled: true
        }
        file: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

// ============================================================================
// Container Registry for AI Foundry
// ============================================================================

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: truncatedCrName
  location: location
  tags: tags
  sku: {
    name: 'Premium'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Disabled'
    networkRuleBypassOptions: 'AzureServices'
    zoneRedundancy: environment == 'prod' ? 'Enabled' : 'Disabled'
    encryption: {
      status: 'disabled'
    }
    dataEndpointEnabled: false
  }
}

// ============================================================================
// AI Foundry Hub (Azure AI Hub workspace)
// ============================================================================

resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: hubName
  location: location
  tags: tags
  kind: 'Hub'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${platformIdentityId}': {}
    }
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  properties: {
    friendlyName: 'Manufacturing & Sales AI Hub (${toUpper(environment)})'
    description: 'AI Foundry hub for Manufacturing and Sales Data Platform - ${toUpper(environment)}'
    keyVault: keyVaultId
    storageAccount: storageAccount.id
    containerRegistry: containerRegistry.id
    applicationInsights: applicationInsightsId
    primaryUserAssignedIdentity: platformIdentityId
    publicNetworkAccess: publicNetworkAccess
    managedNetwork: {
      isolationMode: 'AllowInternetOutbound'
    }
  }
}

// ============================================================================
// AI Foundry Project
// ============================================================================

resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: projectName
  location: location
  tags: tags
  kind: 'Project'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${platformIdentityId}': {}
    }
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  properties: {
    friendlyName: 'Mfg & Sales Data Project (${toUpper(environment)})'
    description: 'AI project for manufacturing and sales analytics use cases'
    hubResourceId: aiHub.id
    primaryUserAssignedIdentity: platformIdentityId
    publicNetworkAccess: publicNetworkAccess
  }
}

// ============================================================================
// Private Endpoint for AI Hub
// ============================================================================

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: privateEndpointNameHub
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointNameHub
        properties: {
          privateLinkServiceId: aiHub.id
          groupIds: [
            'amlworkspace'
          ]
        }
      }
    ]
  }
}

// ============================================================================
// Private Endpoint for Container Registry
// ============================================================================

resource privateEndpointCr 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: '${resourcePrefix}-pe-cr-${environment}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${resourcePrefix}-pe-cr-${environment}'
        properties: {
          privateLinkServiceId: containerRegistry.id
          groupIds: [
            'registry'
          ]
        }
      }
    ]
  }
}

// ============================================================================
// Private Endpoint for Storage Account
// ============================================================================

resource privateEndpointStorage 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: '${resourcePrefix}-pe-stai-${environment}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${resourcePrefix}-pe-stai-${environment}'
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

// ============================================================================
// Diagnostic Settings
// ============================================================================

resource hubDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${hubName}'
  scope: aiHub
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

resource storageDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${truncatedStorageName}'
  scope: storageAccount
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    metrics: [
      {
        category: 'Transaction'
        enabled: true
      }
    ]
  }
}

// ============================================================================
// Outputs
// ============================================================================

output aiHubId string = aiHub.id
output aiHubName string = aiHub.name
output aiProjectId string = aiProject.id
output aiProjectName string = aiProject.name
output storageAccountId string = storageAccount.id
output containerRegistryId string = containerRegistry.id
