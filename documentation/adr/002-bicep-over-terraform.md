# ADR-002: Bicep over Terraform for Infrastructure as Code

## Status

**Accepted** -- 2026-02-28

## Context

We need an Infrastructure as Code (IaC) tool to manage our Azure Data Platform
infrastructure across three environments (Dev, QA, Prod). The platform is Azure-only
with no multi-cloud requirements, and the team is small (4-10 people).

The two leading IaC options for Azure are:

1. **Bicep** -- Azure-native domain-specific language (DSL) that compiles to ARM templates.
   First-party support from Microsoft, deeply integrated with the Azure resource model.

2. **Terraform** -- HashiCorp's multi-cloud IaC tool using the HCL language. Uses the
   AzureRM and AzAPI providers to manage Azure resources.

### Key Evaluation Criteria

| Criteria | Weight | Context |
|----------|--------|---------|
| Azure-native support | High | Day-zero support for new Azure services is critical for Fabric, AI Foundry |
| Learning curve | High | Small team, not all members are IaC experts |
| State management | High | Operational overhead matters for a small team |
| Ecosystem maturity | Medium | Module ecosystem, community, tooling |
| Multi-cloud | Low | Azure-only platform, no current multi-cloud plans |
| CI/CD integration | High | GitHub Actions integration quality |

## Decision

We will use **Bicep** as our IaC language for all Azure infrastructure.

### Rationale

**1. Day-zero Azure resource support**

Bicep compiles to ARM templates and has immediate support for every Azure resource type
and API version on release day. This is critical because our platform uses cutting-edge
Azure services:

- **Microsoft Fabric** -- Bicep supports Fabric capacity resources natively. Terraform's
  AzureRM provider often lags weeks to months behind new resource types.
- **AI Foundry** -- New AI Foundry resource types and properties are available in Bicep
  immediately via ARM API versions.
- **Purview** -- Complex Purview configurations are fully expressible in Bicep.

With Terraform, we would need to use the AzAPI provider as a fallback for unsupported
resources, creating a fragmented codebase mixing AzureRM and AzAPI syntax.

**2. No state file management**

Bicep deployments use the Azure Resource Manager's built-in deployment tracking. There is
no external state file to manage, lock, backup, or recover. This eliminates:

- State storage infrastructure (Terraform requires a Storage Account + container)
- State locking issues during concurrent deployments
- State file corruption recovery procedures
- State import/migration when refactoring modules

For a small team, this operational overhead reduction is significant.

**3. Native What-If support**

Bicep's `what-if` operation uses the ARM API directly, providing accurate change
previews including Azure-side computed properties. Terraform's `plan` is also excellent
but operates against the state file rather than the live Azure state, which can diverge.

**4. Lower learning curve for Azure-focused team**

Bicep's syntax closely mirrors the Azure resource model. Team members familiar with
the Azure portal or ARM templates can read and write Bicep with minimal training. The
official VS Code extension provides IntelliSense, validation, and deployment visualization.

**5. Native GitHub Actions integration**

The `azure/arm-deploy` action provides first-party Bicep deployment support with
validate, what-if, and deploy modes. No third-party actions or binary installations
required.

## Consequences

### Positive

- **Immediate access** to all Azure resource types and API versions on release day.
- **No state file** infrastructure to manage, backup, or recover.
- **Simpler operational model** for a small team.
- **First-party VS Code extension** with rich IntelliSense and error highlighting.
- **Native integration** with Azure Policy, Management Groups, and Azure DevOps / GitHub.
- **Smaller attack surface** -- no state file containing sensitive output values.

### Negative

- **Azure-only** -- If multi-cloud requirements emerge, Bicep cannot manage non-Azure
  resources. This is accepted as the platform is Azure-committed.
- **Less mature module ecosystem** -- Terraform has a larger public module registry.
  However, we build custom modules for our specific architecture, so this is low impact.
- **No drift detection** -- Bicep does not have Terraform's built-in drift detection.
  We mitigate this with periodic what-if checks and Azure Policy compliance scanning.
- **Limited testing frameworks** -- Terraform has established testing patterns (Terratest,
  `terraform test`). Bicep testing is newer and less mature. We use what-if validation
  and deployment validation as our primary testing approach.
- **Team portability** -- Terraform skills are more broadly transferable across cloud
  providers. Bicep skills are Azure-specific. Accepted given our Azure-only strategy.

### Mitigations

- For drift detection, we run scheduled what-if checks and use Azure Policy compliance
  reports.
- For testing, we use Bicep's built-in validation, what-if, and integration tests that
  deploy to a Dev environment and verify resource state.
- If multi-cloud needs emerge (unlikely), we can evaluate Terraform for those specific
  resources while keeping Bicep for Azure-native services.

## Alternatives Rejected

### Terraform with AzureRM Provider

Rejected because:
- Lag in support for new Azure resource types (Fabric, AI Foundry) would require AzAPI
  workarounds
- State management overhead is disproportionate for a small team
- Multi-cloud capability is not needed and does not justify the added complexity
- The team's Azure-native skills align better with Bicep

### Terraform with AzAPI Provider Only

Rejected because:
- AzAPI requires specifying full ARM API JSON payloads, negating Terraform's ergonomic
  advantages
- Still requires state file management
- Worse developer experience than native Bicep

### ARM Templates (JSON)

Rejected because:
- Verbose JSON syntax is error-prone and hard to review
- No module system (linked templates are complex)
- Bicep compiles to ARM templates, so using Bicep gives us the same deployment engine
  with better authoring experience

### Pulumi

Rejected because:
- Smaller community and ecosystem compared to Terraform and Bicep
- Requires a Pulumi Cloud account or self-hosted backend for state
- General-purpose programming languages (TypeScript, Python) add complexity that a
  DSL avoids for infrastructure definitions
- Azure resource support also lags behind ARM/Bicep
