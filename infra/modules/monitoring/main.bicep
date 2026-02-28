// ============================================================================
// Monitoring Module - Log Analytics, Application Insights, Diagnostic Settings
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

@description('Log Analytics workspace retention in days.')
@minValue(30)
@maxValue(730)
param retentionInDays int = 30

@description('Log Analytics workspace SKU.')
@allowed(['PerGB2018', 'CapacityReservation'])
param logAnalyticsSku string = 'PerGB2018'

@description('Daily quota for Log Analytics in GB. -1 = unlimited.')
param dailyQuotaGb int = -1

// ============================================================================
// Variables
// ============================================================================

var logAnalyticsName = '${resourcePrefix}-log-${environment}'
var appInsightsName = '${resourcePrefix}-appi-${environment}'
var actionGroupName = '${resourcePrefix}-ag-platform-${environment}'

// ============================================================================
// Log Analytics Workspace
// ============================================================================

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: logAnalyticsSku
    }
    retentionInDays: retentionInDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    workspaceCapping: dailyQuotaGb > 0 ? {
      dailyQuotaGb: dailyQuotaGb
    } : null
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ============================================================================
// Application Insights (workspace-based)
// ============================================================================

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    RetentionInDays: retentionInDays
    DisableIpMasking: false
    DisableLocalAuth: false
    Flow_Type: 'Bluefield'
    Request_Source: 'rest'
  }
}

// ============================================================================
// Action Group for Alerts
// ============================================================================

resource actionGroup 'Microsoft.Insights/actionGroups@2023-09-01-preview' = {
  name: actionGroupName
  location: 'global'
  tags: tags
  properties: {
    groupShortName: '${resourcePrefix}-${environment}'
    enabled: true
    emailReceivers: []
    smsReceivers: []
    webhookReceivers: []
  }
}

// ============================================================================
// Alert Rules
// ============================================================================

// High Log Analytics Ingestion Alert
resource highIngestionAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${resourcePrefix}-alert-high-ingestion-${environment}'
  location: 'global'
  tags: tags
  properties: {
    description: 'Alert when Log Analytics data ingestion exceeds threshold'
    severity: 2
    enabled: true
    scopes: [
      logAnalyticsWorkspace.id
    ]
    evaluationFrequency: 'PT1H'
    windowSize: 'PT1H'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighIngestion'
          criterionType: 'StaticThresholdCriterion'
          metricNamespace: 'Microsoft.OperationalInsights/workspaces'
          metricName: 'IngestionVolumeMB'
          operator: 'GreaterThan'
          threshold: environment == 'prod' ? 5000 : 1000
          timeAggregation: 'Total'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// ============================================================================
// Saved Queries for the Data Platform
// ============================================================================

resource savedQueryErrors 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: logAnalyticsWorkspace
  name: 'DataPlatformErrors'
  properties: {
    etag: '*'
    displayName: 'Data Platform - All Errors'
    category: 'Data Platform'
    query: 'AzureDiagnostics | where Level == "Error" | project TimeGenerated, ResourceType, Resource, OperationName, ResultDescription | order by TimeGenerated desc'
    version: 2
  }
}

resource savedQueryPostgres 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: logAnalyticsWorkspace
  name: 'PostgreSQLSlowQueries'
  properties: {
    etag: '*'
    displayName: 'PostgreSQL - Slow Queries'
    category: 'Data Platform'
    query: 'AzureDiagnostics | where ResourceType == "FLEXIBLESERVERS" | where Category == "PostgreSQLLogs" | where Message contains "duration" | project TimeGenerated, Resource, Message | order by TimeGenerated desc'
    version: 2
  }
}

resource savedQueryKeyVault 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: logAnalyticsWorkspace
  name: 'KeyVaultOperations'
  properties: {
    etag: '*'
    displayName: 'Key Vault - Access Operations'
    category: 'Data Platform'
    query: 'AzureDiagnostics | where ResourceType == "VAULTS" | project TimeGenerated, OperationName, ResultType, CallerIPAddress, identity_claim_upn_s | order by TimeGenerated desc'
    version: 2
  }
}

// ============================================================================
// Outputs
// ============================================================================

output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
output logAnalyticsWorkspaceName string = logAnalyticsWorkspace.name
output logAnalyticsWorkspaceCustomerId string = logAnalyticsWorkspace.properties.customerId
output applicationInsightsId string = applicationInsights.id
output applicationInsightsName string = applicationInsights.name
output applicationInsightsInstrumentationKey string = applicationInsights.properties.InstrumentationKey
output applicationInsightsConnectionString string = applicationInsights.properties.ConnectionString
output actionGroupId string = actionGroup.id
