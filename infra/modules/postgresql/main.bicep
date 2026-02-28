// ============================================================================
// PostgreSQL Module - Azure Database for PostgreSQL Flexible Server
// with pgvector extension and VNet integration
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

@description('PostgreSQL administrator login.')
@minLength(3)
@maxLength(63)
@secure()
param administratorLogin string

@description('PostgreSQL administrator password.')
@secure()
@minLength(8)
param administratorPassword string

@description('PostgreSQL SKU name.')
@allowed(['Standard_B1ms', 'Standard_B2s', 'Standard_D2s_v3', 'Standard_D4s_v3', 'Standard_D8s_v3'])
param skuName string

@description('PostgreSQL storage size in GB.')
@allowed([32, 64, 128, 256, 512, 1024])
param storageSizeGB int

@description('Subnet ID for VNet integration (delegated to PostgreSQL).')
param dataSubnetId string

@description('Private DNS Zone ID for PostgreSQL.')
param privateDnsZoneId string

@description('Log Analytics Workspace ID for diagnostic settings.')
param logAnalyticsWorkspaceId string

@description('Enable high availability (zone-redundant).')
param highAvailabilityEnabled bool = false

@description('Backup retention period in days.')
@minValue(7)
@maxValue(35)
param backupRetentionDays int = 7

@description('Enable geo-redundant backup.')
param geoRedundantBackup bool = false

@description('PostgreSQL version.')
@allowed(['14', '15', '16'])
param postgresVersion string = '16'

// ============================================================================
// Variables
// ============================================================================

var serverName = '${resourcePrefix}-psql-${environment}'

// Determine SKU tier from SKU name
var skuTier = startsWith(skuName, 'Standard_B') ? 'Burstable' : 'GeneralPurpose'

// ============================================================================
// PostgreSQL Flexible Server
// ============================================================================

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: postgresVersion
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
    storage: {
      storageSizeGB: storageSizeGB
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: geoRedundantBackup ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: highAvailabilityEnabled ? 'ZoneRedundant' : 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: dataSubnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
      publicNetworkAccess: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled'
    }
  }
}

// ============================================================================
// PostgreSQL Extensions - pgvector
// ============================================================================

resource pgvectorExtension 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'azure.extensions'
  properties: {
    value: 'VECTOR,UUID-OSSP,PGCRYPTO'
    source: 'user-override'
  }
}

// ============================================================================
// PostgreSQL Server Configuration
// ============================================================================

resource sharedPreloadLibraries 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'shared_preload_libraries'
  properties: {
    value: 'pg_stat_statements'
    source: 'user-override'
  }
  dependsOn: [
    pgvectorExtension
  ]
}

resource logCheckpoints 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'log_checkpoints'
  properties: {
    value: 'on'
    source: 'user-override'
  }
  dependsOn: [
    sharedPreloadLibraries
  ]
}

resource logConnections 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'log_connections'
  properties: {
    value: 'on'
    source: 'user-override'
  }
  dependsOn: [
    logCheckpoints
  ]
}

resource connectionThrottling 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'connection_throttle.enable'
  properties: {
    value: 'on'
    source: 'user-override'
  }
  dependsOn: [
    logConnections
  ]
}

// ============================================================================
// PostgreSQL Databases
// ============================================================================

resource manufacturingDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgresServer
  name: 'manufacturing_db'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
  dependsOn: [
    connectionThrottling
  ]
}

resource salesDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgresServer
  name: 'sales_db'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
  dependsOn: [
    manufacturingDb
  ]
}

resource vectorDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgresServer
  name: 'vector_db'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
  dependsOn: [
    salesDb
  ]
}

// ============================================================================
// Diagnostic Settings
// ============================================================================

resource diagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${serverName}'
  scope: postgresServer
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

output serverId string = postgresServer.id
output serverName string = postgresServer.name
output fqdn string = postgresServer.properties.fullyQualifiedDomainName
output manufacturingDbName string = manufacturingDb.name
output salesDbName string = salesDb.name
output vectorDbName string = vectorDb.name
