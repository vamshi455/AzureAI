// ============================================================================
// Storage Module - ADLS Gen2 Lakehouse with Private Endpoint
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

@description('Principal ID of the data ingestion managed identity.')
param dataIngestionIdentityPrincipalId string

@description('Principal ID of the app service managed identity.')
param appServiceIdentityPrincipalId string

@description('Subnet ID for the private endpoint.')
param privateEndpointSubnetId string

@description('Log Analytics Workspace ID for diagnostic settings.')
param logAnalyticsWorkspaceId string

@description('Private DNS Zone ID for blob.')
param blobPrivateDnsZoneId string

@description('Private DNS Zone ID for DFS.')
param dfsPrivateDnsZoneId string

// ============================================================================
// Variables
// ============================================================================

// Storage account names: 3-24 chars, lowercase alphanumeric only
var rawStorageName = '${resourcePrefix}stlake${environment}${uniqueString(resourceGroup().id)}'
var storageName = length(rawStorageName) > 24 ? substring(rawStorageName, 0, 24) : rawStorageName
var privateEndpointBlobName = '${resourcePrefix}-pe-blob-${environment}'
var privateEndpointDfsName = '${resourcePrefix}-pe-dfs-${environment}'

var isProd = environment == 'prod'

// Container names for medallion architecture
var containers = [
  'bronze'
  'silver'
  'gold'
  'rag-documents'
]

// ============================================================================
// Storage Account (ADLS Gen2)
// ============================================================================

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: union(tags, { Purpose: 'Lakehouse' })
  kind: 'StorageV2'
  sku: {
    name: isProd ? 'Standard_GRS' : 'Standard_LRS'
  }
  properties: {
    isHnsEnabled: true
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: !isProd
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: isProd ? 'Disabled' : 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: isProd ? 'Deny' : 'Allow'
    }
  }
}

// ============================================================================
// Blob Service + Containers
// ============================================================================

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: isProd ? 30 : 7
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: isProd ? 30 : 7
    }
  }
}

resource storageContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for containerName in containers: {
    parent: blobService
    name: containerName
    properties: {
      publicAccess: 'None'
    }
  }
]

// ============================================================================
// RBAC Role Assignments
// ============================================================================

// Data ingestion identity gets Storage Blob Data Contributor
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource dataIngestionRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, dataIngestionIdentityPrincipalId, storageBlobDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: dataIngestionIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// App service identity gets Storage Blob Data Reader
var storageBlobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource appServiceRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, appServiceIdentityPrincipalId, storageBlobDataReaderRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReaderRoleId)
    principalId: appServiceIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Private Endpoints
// ============================================================================

resource privateEndpointBlob 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: privateEndpointBlobName
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointBlobName
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

resource privateEndpointDfs 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: privateEndpointDfsName
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointDfsName
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: [
            'dfs'
          ]
        }
      }
    ]
  }
}

resource blobDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: privateEndpointBlob
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-blob-core-windows-net'
        properties: {
          privateDnsZoneId: blobPrivateDnsZoneId
        }
      }
    ]
  }
}

resource dfsDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: privateEndpointDfs
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-dfs-core-windows-net'
        properties: {
          privateDnsZoneId: dfsPrivateDnsZoneId
        }
      }
    ]
  }
}

// ============================================================================
// Diagnostic Settings
// ============================================================================

resource diagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${storageName}'
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

resource blobDiagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${storageName}-blob'
  scope: blobService
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'StorageRead'
        enabled: true
      }
      {
        category: 'StorageWrite'
        enabled: true
      }
      {
        category: 'StorageDelete'
        enabled: true
      }
    ]
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

output storageAccountId string = storageAccount.id
output storageAccountName string = storageAccount.name
output primaryBlobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output primaryDfsEndpoint string = storageAccount.properties.primaryEndpoints.dfs
output privateEndpointBlobId string = privateEndpointBlob.id
output privateEndpointDfsId string = privateEndpointDfs.id
