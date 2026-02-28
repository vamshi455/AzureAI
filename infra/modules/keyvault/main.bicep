// ============================================================================
// Key Vault Module - Azure Key Vault with Private Endpoint
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

@description('Object ID of the Key Vault admin (AAD user or group).')
param adminObjectId string

@description('Principal ID of the platform managed identity.')
param platformIdentityPrincipalId string

@description('Subnet ID for the private endpoint.')
param privateEndpointSubnetId string

@description('Log Analytics Workspace ID for diagnostic settings.')
param logAnalyticsWorkspaceId string

@description('Enable purge protection (should be true for production).')
param enablePurgeProtection bool = false

@description('Soft delete retention in days.')
@minValue(7)
@maxValue(90)
param softDeleteRetentionInDays int = 90

// ============================================================================
// Variables
// ============================================================================

// Key Vault names have a 24-char limit and must be globally unique
var keyVaultName = '${resourcePrefix}-kv-${environment}-${uniqueString(resourceGroup().id)}'
var truncatedKvName = length(keyVaultName) > 24 ? substring(keyVaultName, 0, 24) : keyVaultName
var privateEndpointName = '${resourcePrefix}-pe-kv-${environment}'

// ============================================================================
// Key Vault
// ============================================================================

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: truncatedKvName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: softDeleteRetentionInDays
    enablePurgeProtection: enablePurgeProtection ? true : null
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

// ============================================================================
// Role Assignments (RBAC-based access)
// ============================================================================

// Admin gets Key Vault Administrator role
var keyVaultAdministratorRoleId = '00482a5a-887f-4fb3-b363-3b7fe8e74483'

resource adminRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, adminObjectId, keyVaultAdministratorRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultAdministratorRoleId)
    principalId: adminObjectId
    principalType: 'Group'
  }
}

// Platform identity gets Key Vault Secrets Officer
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource platformRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, platformIdentityPrincipalId, keyVaultSecretsOfficerRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
    principalId: platformIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Private Endpoint
// ============================================================================

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: privateEndpointName
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointName
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: [
            'vault'
          ]
        }
      }
    ]
  }
}

resource privateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.vaultcore.azure.net'
}

resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-vaultcore-azure-net'
        properties: {
          privateDnsZoneId: privateDnsZone.id
        }
      }
    ]
  }
}

// ============================================================================
// Diagnostic Settings
// ============================================================================

resource diagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${truncatedKvName}'
  scope: keyVault
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
      {
        categoryGroup: 'audit'
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

output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output privateEndpointId string = privateEndpoint.id
