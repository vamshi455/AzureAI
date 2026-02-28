// ============================================================================
// Purview Module - Microsoft Purview Account with Managed VNet
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

@description('Principal ID of the platform managed identity for role assignment.')
param platformIdentityPrincipalId string

// ============================================================================
// Variables
// ============================================================================

var purviewAccountName = '${resourcePrefix}-pview-${environment}'
var privateEndpointAccountName = '${resourcePrefix}-pe-pview-account-${environment}'
var privateEndpointPortalName = '${resourcePrefix}-pe-pview-portal-${environment}'

// ============================================================================
// Purview Account
// ============================================================================

resource purviewAccount 'Microsoft.Purview/accounts@2021-12-01' = {
  name: purviewAccountName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publicNetworkAccess: 'Disabled'
    managedResourceGroupName: '${resourcePrefix}-rg-pview-managed-${environment}'
  }
}

// ============================================================================
// Role Assignments
// ============================================================================

// Purview Data Curator role for the platform identity
var purviewDataCuratorRoleId = 'e89c7235-2f73-4c5c-9a04-3a80c8412708'

resource purviewDataCuratorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(purviewAccount.id, platformIdentityPrincipalId, purviewDataCuratorRoleId)
  scope: purviewAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', purviewDataCuratorRoleId)
    principalId: platformIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Reader role for the Purview system-assigned identity on the resource group
var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'

resource purviewReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, purviewAccount.id, readerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRoleId)
    principalId: purviewAccount.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Blob Data Reader for the Purview system-assigned identity
var storageBlobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource purviewStorageAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, purviewAccount.id, storageBlobDataReaderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReaderRoleId)
    principalId: purviewAccount.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Private Endpoints
// ============================================================================

// Account endpoint
resource privateEndpointAccount 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: privateEndpointAccountName
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointAccountName
        properties: {
          privateLinkServiceId: purviewAccount.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

// Portal endpoint
resource privateEndpointPortal 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: privateEndpointPortalName
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointPortalName
        properties: {
          privateLinkServiceId: purviewAccount.id
          groupIds: [
            'portal'
          ]
        }
      }
    ]
  }
}

// DNS Zone Groups
resource accountDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: privateEndpointAccount
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-purview-azure-com'
        properties: {
          privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.purview.azure.com')
        }
      }
    ]
  }
}

resource portalDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: privateEndpointPortal
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-purview-azure-com'
        properties: {
          privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.purview.azure.com')
        }
      }
    ]
  }
}

// ============================================================================
// Diagnostic Settings
// ============================================================================

resource diagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${purviewAccountName}'
  scope: purviewAccount
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

// ============================================================================
// Outputs
// ============================================================================

output purviewAccountId string = purviewAccount.id
output purviewAccountName string = purviewAccount.name
output purviewIdentityPrincipalId string = purviewAccount.identity.principalId
output purviewScanEndpoint string = purviewAccount.properties.endpoints.scan
output purviewCatalogEndpoint string = purviewAccount.properties.endpoints.catalog
