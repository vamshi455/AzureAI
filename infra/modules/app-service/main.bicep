// ============================================================================
// App Service Module - App Service Plan + Web Apps (Streamlit & React)
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

@description('App Service Plan SKU.')
@allowed(['B1', 'B2', 'B3', 'S1', 'S2', 'S3', 'P1v3', 'P2v3', 'P3v3'])
param appServicePlanSku string

@description('App Service subnet ID for VNet integration.')
param appServiceSubnetId string

@description('Private endpoint subnet ID.')
param privateEndpointSubnetId string

@description('VNet ID for private DNS zone link.')
param vnetId string

@description('Log Analytics Workspace ID for diagnostic settings.')
param logAnalyticsWorkspaceId string

@description('Application Insights connection string.')
param applicationInsightsConnectionString string

@description('Platform managed identity resource ID.')
param platformIdentityId string

@description('Key Vault URI for secret references.')
param keyVaultUri string

@description('PostgreSQL FQDN.')
param postgresqlFqdn string

@description('Number of workers for the App Service Plan.')
@minValue(1)
@maxValue(30)
param workerCount int = environment == 'prod' ? 3 : 1

// ============================================================================
// Variables
// ============================================================================

var appServicePlanName = '${resourcePrefix}-asp-${environment}'
var streamlitAppName = '${resourcePrefix}-app-streamlit-${environment}'
var reactAppName = '${resourcePrefix}-app-react-${environment}'

// Map SKU string to tier
var skuTier = startsWith(appServicePlanSku, 'B') ? 'Basic' : startsWith(appServicePlanSku, 'S') ? 'Standard' : 'PremiumV3'

// ============================================================================
// App Service Plan
// ============================================================================

resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: appServicePlanSku
    tier: skuTier
    capacity: workerCount
  }
  properties: {
    reserved: true
    zoneRedundant: environment == 'prod' && startsWith(appServicePlanSku, 'P') ? true : false
  }
}

// ============================================================================
// Streamlit Web App (Python)
// ============================================================================

resource streamlitApp 'Microsoft.Web/sites@2023-12-01' = {
  name: streamlitAppName
  location: location
  tags: union(tags, { Application: 'Streamlit Dashboard' })
  kind: 'app,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${platformIdentityId}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    publicNetworkAccess: 'Disabled'
    virtualNetworkSubnetId: appServiceSubnetId
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      healthCheckPath: '/healthz'
      appCommandLine: 'streamlit run app.py --server.port 8000 --server.address 0.0.0.0'
      appSettings: [
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: applicationInsightsConnectionString
        }
        {
          name: 'AZURE_KEYVAULT_URI'
          value: keyVaultUri
        }
        {
          name: 'POSTGRESQL_HOST'
          value: postgresqlFqdn
        }
        {
          name: 'POSTGRESQL_DATABASE'
          value: 'manufacturing_db'
        }
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'ENVIRONMENT'
          value: environment
        }
      ]
    }
  }
}

// ============================================================================
// React Web App (Node.js)
// ============================================================================

resource reactApp 'Microsoft.Web/sites@2023-12-01' = {
  name: reactAppName
  location: location
  tags: union(tags, { Application: 'React Dashboard' })
  kind: 'app,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${platformIdentityId}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    publicNetworkAccess: 'Disabled'
    virtualNetworkSubnetId: appServiceSubnetId
    siteConfig: {
      linuxFxVersion: 'NODE|20-lts'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      healthCheckPath: '/health'
      appSettings: [
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: applicationInsightsConnectionString
        }
        {
          name: 'WEBSITE_NODE_DEFAULT_VERSION'
          value: '~20'
        }
        {
          name: 'REACT_APP_API_BASE_URL'
          value: 'https://${streamlitAppName}.azurewebsites.net'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'ENVIRONMENT'
          value: environment
        }
      ]
    }
  }
}

// ============================================================================
// Staging Slots (Production only)
// ============================================================================

resource streamlitStagingSlot 'Microsoft.Web/sites/slots@2023-12-01' = if (environment == 'prod') {
  parent: streamlitApp
  name: 'staging'
  location: location
  tags: union(tags, { Slot: 'staging' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${platformIdentityId}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      autoSwapSlotName: 'production'
    }
  }
}

resource reactStagingSlot 'Microsoft.Web/sites/slots@2023-12-01' = if (environment == 'prod') {
  parent: reactApp
  name: 'staging'
  location: location
  tags: union(tags, { Slot: 'staging' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${platformIdentityId}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'NODE|20-lts'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      autoSwapSlotName: 'production'
    }
  }
}

// ============================================================================
// Private Endpoints
// ============================================================================

resource streamlitPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: '${resourcePrefix}-pe-app-streamlit-${environment}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${resourcePrefix}-pe-app-streamlit-${environment}'
        properties: {
          privateLinkServiceId: streamlitApp.id
          groupIds: [
            'sites'
          ]
        }
      }
    ]
  }
}

resource reactPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: '${resourcePrefix}-pe-app-react-${environment}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${resourcePrefix}-pe-app-react-${environment}'
        properties: {
          privateLinkServiceId: reactApp.id
          groupIds: [
            'sites'
          ]
        }
      }
    ]
  }
}

// Private DNS Zone Groups
resource streamlitDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: streamlitPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-azurewebsites-net'
        properties: {
          privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.azurewebsites.net')
        }
      }
    ]
  }
}

resource reactDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: reactPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-azurewebsites-net'
        properties: {
          privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.azurewebsites.net')
        }
      }
    ]
  }
}

// ============================================================================
// Diagnostic Settings
// ============================================================================

resource appServicePlanDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${appServicePlanName}'
  scope: appServicePlan
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

resource streamlitDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${streamlitAppName}'
  scope: streamlitApp
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'AppServiceHTTPLogs'
        enabled: true
      }
      {
        category: 'AppServiceConsoleLogs'
        enabled: true
      }
      {
        category: 'AppServiceAppLogs'
        enabled: true
      }
      {
        category: 'AppServicePlatformLogs'
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

resource reactDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${reactAppName}'
  scope: reactApp
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'AppServiceHTTPLogs'
        enabled: true
      }
      {
        category: 'AppServiceConsoleLogs'
        enabled: true
      }
      {
        category: 'AppServiceAppLogs'
        enabled: true
      }
      {
        category: 'AppServicePlatformLogs'
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

output appServicePlanId string = appServicePlan.id
output appServicePlanName string = appServicePlan.name
output streamlitAppId string = streamlitApp.id
output streamlitAppName string = streamlitApp.name
output streamlitAppDefaultHostname string = streamlitApp.properties.defaultHostName
output reactAppId string = reactApp.id
output reactAppName string = reactApp.name
output reactAppDefaultHostname string = reactApp.properties.defaultHostName
