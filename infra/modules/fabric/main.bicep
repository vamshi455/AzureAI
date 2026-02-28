// ============================================================================
// Fabric Module - Microsoft Fabric Capacity
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

@description('Fabric capacity SKU.')
@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64', 'F128', 'F256', 'F512', 'F1024'])
param skuName string

@description('Fabric capacity admin members (UPNs of AAD users).')
param adminMembers array

// ============================================================================
// Variables
// ============================================================================

var capacityName = '${resourcePrefix}fabric${environment}'

// ============================================================================
// Fabric Capacity
// ============================================================================

resource fabricCapacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: capacityName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: adminMembers
    }
  }
}

// ============================================================================
// Outputs
// ============================================================================

output capacityId string = fabricCapacity.id
output capacityName string = fabricCapacity.name
