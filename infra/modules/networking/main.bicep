// ============================================================================
// Networking Module - Hub-Spoke VNet with NSGs, Subnets, and Peering
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

@description('Hub VNet address space.')
param hubVnetAddressSpace string

@description('Spoke VNet address space.')
param spokeVnetAddressSpace string

@description('Log Analytics Workspace ID for diagnostic settings.')
param logAnalyticsWorkspaceId string

// ============================================================================
// Variables
// ============================================================================

var hubVnetName = '${resourcePrefix}-vnet-hub-${environment}'
var spokeVnetName = '${resourcePrefix}-vnet-spoke-${environment}'

// Parse the base address from the spoke address space for subnet calculation
// Spoke: 10.1.0.0/16 -> subnets within
var spokeSubnets = {
  fabric: {
    name: 'snet-fabric'
    addressPrefix: cidrSubnet(spokeVnetAddressSpace, 24, 0)       // /24 - e.g., 10.1.0.0/24
  }
  privateEndpoints: {
    name: 'snet-private-endpoints'
    addressPrefix: cidrSubnet(spokeVnetAddressSpace, 24, 1)       // /24 - e.g., 10.1.1.0/24
  }
  appService: {
    name: 'snet-app-service'
    addressPrefix: cidrSubnet(spokeVnetAddressSpace, 24, 2)       // /24 - e.g., 10.1.2.0/24
  }
  data: {
    name: 'snet-data'
    addressPrefix: cidrSubnet(spokeVnetAddressSpace, 24, 3)       // /24 - e.g., 10.1.3.0/24
  }
  selfHostedIr: {
    name: 'snet-self-hosted-ir'
    addressPrefix: cidrSubnet(spokeVnetAddressSpace, 24, 4)       // /24 - e.g., 10.1.4.0/24
  }
}

var hubSubnets = {
  gateway: {
    name: 'GatewaySubnet'
    addressPrefix: cidrSubnet(hubVnetAddressSpace, 24, 0)
  }
  firewall: {
    name: 'AzureFirewallSubnet'
    addressPrefix: cidrSubnet(hubVnetAddressSpace, 24, 1)
  }
  bastion: {
    name: 'AzureBastionSubnet'
    addressPrefix: cidrSubnet(hubVnetAddressSpace, 24, 2)
  }
}

// ============================================================================
// Network Security Groups
// ============================================================================

resource nsgFabric 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: '${resourcePrefix}-nsg-fabric-${environment}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowHTTPSOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'Internet'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource nsgPrivateEndpoints 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: '${resourcePrefix}-nsg-pe-${environment}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowVnetInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'VirtualNetwork'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource nsgAppService 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: '${resourcePrefix}-nsg-appsvc-${environment}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowHTTPSInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowHTTPInbound'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource nsgData 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: '${resourcePrefix}-nsg-data-${environment}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowPostgreSQLInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5432'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'VirtualNetwork'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource nsgSelfHostedIr 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: '${resourcePrefix}-nsg-shir-${environment}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowHTTPSOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'AzureCloud'
        }
      }
      {
        name: 'AllowServiceBusOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5671-5672'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'ServiceBus'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// ============================================================================
// NSG Diagnostic Settings
// ============================================================================

resource nsgFabricDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${nsgFabric.name}'
  scope: nsgFabric
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

resource nsgPeDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${nsgPrivateEndpoints.name}'
  scope: nsgPrivateEndpoints
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

resource nsgAppSvcDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${nsgAppService.name}'
  scope: nsgAppService
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

resource nsgDataDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${nsgData.name}'
  scope: nsgData
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

resource nsgShirDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${nsgSelfHostedIr.name}'
  scope: nsgSelfHostedIr
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

// ============================================================================
// Hub VNet
// ============================================================================

resource hubVnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: hubVnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        hubVnetAddressSpace
      ]
    }
    subnets: [
      {
        name: hubSubnets.gateway.name
        properties: {
          addressPrefix: hubSubnets.gateway.addressPrefix
        }
      }
      {
        name: hubSubnets.firewall.name
        properties: {
          addressPrefix: hubSubnets.firewall.addressPrefix
        }
      }
      {
        name: hubSubnets.bastion.name
        properties: {
          addressPrefix: hubSubnets.bastion.addressPrefix
        }
      }
    ]
  }
}

// ============================================================================
// Spoke VNet
// ============================================================================

resource spokeVnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: spokeVnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        spokeVnetAddressSpace
      ]
    }
    subnets: [
      {
        name: spokeSubnets.fabric.name
        properties: {
          addressPrefix: spokeSubnets.fabric.addressPrefix
          networkSecurityGroup: {
            id: nsgFabric.id
          }
        }
      }
      {
        name: spokeSubnets.privateEndpoints.name
        properties: {
          addressPrefix: spokeSubnets.privateEndpoints.addressPrefix
          networkSecurityGroup: {
            id: nsgPrivateEndpoints.id
          }
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: spokeSubnets.appService.name
        properties: {
          addressPrefix: spokeSubnets.appService.addressPrefix
          networkSecurityGroup: {
            id: nsgAppService.id
          }
          delegations: [
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
      {
        name: spokeSubnets.data.name
        properties: {
          addressPrefix: spokeSubnets.data.addressPrefix
          networkSecurityGroup: {
            id: nsgData.id
          }
          delegations: [
            {
              name: 'Microsoft.DBforPostgreSQL.flexibleServers'
              properties: {
                serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
              }
            }
          ]
        }
      }
      {
        name: spokeSubnets.selfHostedIr.name
        properties: {
          addressPrefix: spokeSubnets.selfHostedIr.addressPrefix
          networkSecurityGroup: {
            id: nsgSelfHostedIr.id
          }
        }
      }
    ]
  }
}

// ============================================================================
// VNet Diagnostic Settings
// ============================================================================

resource hubVnetDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${hubVnetName}'
  scope: hubVnet
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

resource spokeVnetDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${spokeVnetName}'
  scope: spokeVnet
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
// VNet Peering (Hub <-> Spoke)
// ============================================================================

resource hubToSpokePeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-01-01' = {
  parent: hubVnet
  name: 'peer-hub-to-spoke-${environment}'
  properties: {
    remoteVirtualNetwork: {
      id: spokeVnet.id
    }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
  }
}

resource spokeToHubPeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-01-01' = {
  parent: spokeVnet
  name: 'peer-spoke-to-hub-${environment}'
  properties: {
    remoteVirtualNetwork: {
      id: hubVnet.id
    }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

// ============================================================================
// Private DNS Zones
// ============================================================================

resource privateDnsZoneKeyVault 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}

resource privateDnsZonePostgres 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource privateDnsZoneWebApps 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.azurewebsites.net'
  location: 'global'
  tags: tags
}

resource privateDnsZonePurview 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.purview.azure.com'
  location: 'global'
  tags: tags
}

resource privateDnsZoneCognitiveServices 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
  tags: tags
}

resource privateDnsZoneOpenAI 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.openai.azure.com'
  location: 'global'
  tags: tags
}

// ============================================================================
// Private DNS Zone VNet Links
// ============================================================================

resource dnsLinkKeyVault 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZoneKeyVault
  name: 'link-${spokeVnetName}'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: spokeVnet.id
    }
    registrationEnabled: false
  }
}

resource dnsLinkPostgres 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZonePostgres
  name: 'link-${spokeVnetName}'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: spokeVnet.id
    }
    registrationEnabled: false
  }
}

resource dnsLinkWebApps 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZoneWebApps
  name: 'link-${spokeVnetName}'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: spokeVnet.id
    }
    registrationEnabled: false
  }
}

resource dnsLinkPurview 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZonePurview
  name: 'link-${spokeVnetName}'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: spokeVnet.id
    }
    registrationEnabled: false
  }
}

resource dnsLinkCognitive 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZoneCognitiveServices
  name: 'link-${spokeVnetName}'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: spokeVnet.id
    }
    registrationEnabled: false
  }
}

resource dnsLinkOpenAI 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZoneOpenAI
  name: 'link-${spokeVnetName}'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: spokeVnet.id
    }
    registrationEnabled: false
  }
}

// ============================================================================
// Outputs
// ============================================================================

output hubVnetId string = hubVnet.id
output hubVnetName string = hubVnet.name
output spokeVnetId string = spokeVnet.id
output spokeVnetName string = spokeVnet.name

output fabricSubnetId string = spokeVnet.properties.subnets[0].id
output privateEndpointSubnetId string = spokeVnet.properties.subnets[1].id
output appServiceSubnetId string = spokeVnet.properties.subnets[2].id
output dataSubnetId string = spokeVnet.properties.subnets[3].id
output selfHostedIrSubnetId string = spokeVnet.properties.subnets[4].id

output keyVaultPrivateDnsZoneId string = privateDnsZoneKeyVault.id
output postgresPrivateDnsZoneId string = privateDnsZonePostgres.id
output webAppsPrivateDnsZoneId string = privateDnsZoneWebApps.id
output purviewPrivateDnsZoneId string = privateDnsZonePurview.id
output cognitiveServicesPrivateDnsZoneId string = privateDnsZoneCognitiveServices.id
output openAIPrivateDnsZoneId string = privateDnsZoneOpenAI.id
