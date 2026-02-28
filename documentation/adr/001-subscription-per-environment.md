# ADR-001: Subscription-per-Environment over Resource-Group-per-Environment

## Status

**Accepted** -- 2026-02-28

## Context

We need to isolate our three environments (Dev, QA, Prod) within Azure. The two primary
patterns for environment isolation are:

1. **Resource-Group-per-Environment** -- A single Azure subscription with separate resource
   groups for each environment (e.g., `rg-*-dev`, `rg-*-qa`, `rg-*-prod`).

2. **Subscription-per-Environment** -- Separate Azure subscriptions for each environment,
   organized under a Management Group hierarchy.

Our platform includes Microsoft Fabric, Purview, AI Foundry, PostgreSQL, and several
application services. The team is small (4-10 people) but the platform handles sensitive
manufacturing and sales data, and production reliability is critical.

### Factors Considered

- **Blast radius containment** -- A misconfiguration or runaway process in Dev should not
  be able to impact Prod resources, quotas, or rate limits.

- **RBAC boundaries** -- Subscription-level RBAC provides a stronger isolation boundary.
  Some Azure roles (e.g., Contributor at the subscription level) cannot be scoped to a
  single resource group without granting broader permissions than intended.

- **Azure Policy enforcement** -- Policies like "no public endpoints" should apply only to
  Prod. Subscription-level policy assignment makes this clean and auditable.

- **Cost management** -- Subscription-level cost views, budgets, and alerts are the
  natural unit for Azure Cost Management. Splitting by resource group tags works but
  requires more discipline and is error-prone.

- **Quota and rate limits** -- Azure API rate limits and resource quotas apply at the
  subscription level. A heavy Dev workload could exhaust quotas needed by Prod in a
  shared subscription.

- **Fabric capacity isolation** -- Microsoft Fabric capacities are subscription-scoped.
  Separate subscriptions ensure independent capacity management.

- **Compliance readiness** -- Separate subscriptions provide clear audit boundaries if
  compliance requirements (SOC 2, ISO 27001) emerge.

## Decision

We will use **subscription-per-environment** with the following layout:

| Subscription | Environments | Purpose |
|-------------|-------------|---------|
| Sub-Platform | N/A | Shared services (hub networking, DNS, monitoring) |
| Sub-DataPlatform-NonProd | Dev, QA | Non-production workloads |
| Sub-DataPlatform-Prod | Prod | Production workloads |

Dev and QA share a subscription (Sub-DataPlatform-NonProd) because:
- They have similar security postures (relaxed relative to Prod)
- Sharing reduces subscription sprawl for a small team
- Resource group-level isolation within the subscription is sufficient for Dev vs. QA
- Cost savings from shared Purview account and networking resources

Prod has its own subscription because:
- Strongest possible isolation from non-production workloads
- Independent quotas, policies, and RBAC
- Clean compliance boundary
- Separate billing and cost management

## Consequences

### Positive

- **Strong Prod isolation** -- No accidental cross-environment impact from Dev/QA.
- **Clean policy enforcement** -- Strict policies (no public endpoints, CMK encryption)
  apply only at the Prod subscription level.
- **Independent quotas** -- Dev experimentation cannot exhaust Prod quotas.
- **Clear cost attribution** -- Per-subscription cost management with no tag-based
  gymnastics.
- **Audit readiness** -- Clear subscription boundaries simplify compliance evidence
  collection.

### Negative

- **More subscriptions to manage** -- Three subscriptions (plus potential future ones)
  require Management Group organization and cross-subscription networking.
- **Cross-subscription complexity** -- Private DNS zones, VNet peering, and shared
  services require cross-subscription configuration.
- **CI/CD complexity** -- Each environment needs its own service principal / federated
  credential for OIDC authentication.
- **Slight overhead for a small team** -- The team must manage multiple subscription
  contexts, though IaC (Bicep) abstracts most of this.

### Mitigations

- Management Group hierarchy with inherited policies reduces per-subscription policy work.
- Hub-spoke networking centralizes DNS and routing in the Platform subscription.
- GitHub Actions environment secrets abstract per-subscription credentials.
- Bicep parameterization handles per-environment configuration differences.

## Alternatives Rejected

### Single Subscription with Resource Groups

Simpler to set up but rejected because:
- Quotas shared across all environments (risk of Dev impacting Prod)
- RBAC boundaries weaker (subscription-level roles span all environments)
- Policy enforcement less granular (harder to apply Prod-only policies)
- Cost management requires tag discipline rather than natural subscription boundaries
- Fabric capacity not independently manageable

### Subscription-per-Environment (Separate Dev and QA)

Four subscriptions (Platform, Dev, QA, Prod) was considered but rejected because:
- Additional subscription overhead for a small team with no current compliance mandate
  differentiating Dev from QA
- Dev and QA have identical security postures
- Can be split later if needed with manageable migration effort
