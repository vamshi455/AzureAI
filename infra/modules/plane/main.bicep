// ============================================================================
// Plane Module - Container App for Plane (open-source ticketing)
// with PostgreSQL backend
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

@description('Plane container image tag.')
param imageTag string = 'latest'

@description('App subnet ID for Container App environment.')
param appSubnetId string

@description('Log Analytics Workspace ID for diagnostic settings.')
param logAnalyticsWorkspaceId string

@description('Minimum number of replicas.')
@minValue(0)
@maxValue(10)
param minReplicas int = environment == 'prod' ? 2 : 1

@description('Maximum number of replicas.')
@minValue(1)
@maxValue(30)
param maxReplicas int = environment == 'prod' ? 10 : 3

@description('CPU allocation for the container.')
param containerCpu string = '0.5'

@description('Memory allocation for the container.')
param containerMemory string = '1Gi'

@description('PostgreSQL administrator password for Plane database.')
@secure()
param planePostgresPassword string

// ============================================================================
// Variables
// ============================================================================

var containerAppEnvName = '${resourcePrefix}-cae-plane-${environment}'
var containerAppApiName = '${resourcePrefix}-ca-plane-api-${environment}'
var containerAppWebName = '${resourcePrefix}-ca-plane-web-${environment}'
var containerAppWorkerName = '${resourcePrefix}-ca-plane-worker-${environment}'
var postgresServerName = '${resourcePrefix}-psql-plane-${environment}'

// ============================================================================
// PostgreSQL Flexible Server for Plane
// ============================================================================

resource planePostgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresServerName
  location: location
  tags: union(tags, { Application: 'Plane' })
  sku: {
    name: environment == 'prod' ? 'Standard_D2s_v3' : 'Standard_B1ms'
    tier: environment == 'prod' ? 'GeneralPurpose' : 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: 'planeadmin'
    administratorLoginPassword: planePostgresPassword
    storage: {
      storageSizeGB: environment == 'prod' ? 128 : 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: environment == 'prod' ? 35 : 7
      geoRedundantBackup: environment == 'prod' ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: environment == 'prod' ? 'ZoneRedundant' : 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Disabled'
    }
  }
}

resource planeDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: planePostgres
  name: 'plane'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// ============================================================================
// Container App Environment
// ============================================================================

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: split(logAnalyticsWorkspaceId, '/')[8]
}

resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppEnvName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: appSubnetId
      internal: true
    }
    zoneRedundant: environment == 'prod'
  }
}

// ============================================================================
// Plane API Container App
// ============================================================================

resource planeApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppApiName
  location: location
  tags: union(tags, { Application: 'Plane API' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      ingress: {
        external: false
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'database-url'
          value: 'postgresql://planeadmin@${planePostgres.name}:CHANGE_ME_IN_KEYVAULT@${planePostgres.properties.fullyQualifiedDomainName}:5432/plane?sslmode=require'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'plane-api'
          image: 'makeplane/plane-backend:${imageTag}'
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'DJANGO_SETTINGS_MODULE'
              value: 'plane.settings.production'
            }
            {
              name: 'CORS_ALLOWED_ORIGINS'
              value: 'https://${containerAppWebName}.${containerAppEnvironment.properties.defaultDomain}'
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

// ============================================================================
// Plane Web Container App
// ============================================================================

resource planeWeb 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppWebName
  location: location
  tags: union(tags, { Application: 'Plane Web' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 3000
        transport: 'http'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'plane-web'
          image: 'makeplane/plane-frontend:${imageTag}'
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'NEXT_PUBLIC_API_BASE_URL'
              value: 'https://${containerAppApiName}.${containerAppEnvironment.properties.defaultDomain}'
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

// ============================================================================
// Plane Worker Container App
// ============================================================================

resource planeWorker 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppWorkerName
  location: location
  tags: union(tags, { Application: 'Plane Worker' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      secrets: [
        {
          name: 'database-url'
          value: 'postgresql://planeadmin@${planePostgres.name}:CHANGE_ME_IN_KEYVAULT@${planePostgres.properties.fullyQualifiedDomainName}:5432/plane?sslmode=require'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'plane-worker'
          image: 'makeplane/plane-backend:${imageTag}'
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          command: [
            'python'
            'manage.py'
            'rqworker'
          ]
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'DJANGO_SETTINGS_MODULE'
              value: 'plane.settings.production'
            }
          ]
        }
      ]
      scale: {
        minReplicas: environment == 'prod' ? 1 : 0
        maxReplicas: environment == 'prod' ? 5 : 2
      }
    }
  }
}

// ============================================================================
// Diagnostic Settings
// ============================================================================

resource planePostgresDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${postgresServerName}'
  scope: planePostgres
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

output containerAppEnvironmentId string = containerAppEnvironment.id
output planeApiUrl string = 'https://${planeApi.properties.configuration.ingress.fqdn}'
output planeWebUrl string = 'https://${planeWeb.properties.configuration.ingress.fqdn}'
output planePostgresServerId string = planePostgres.id
output planePostgresFqdn string = planePostgres.properties.fullyQualifiedDomainName
