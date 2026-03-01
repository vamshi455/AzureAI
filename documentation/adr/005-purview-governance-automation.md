# ADR-005: Purview Governance Automation Approach

## Status

Accepted

## Date

2026-03-01

## Context

The platform requires data governance configuration in Microsoft Purview following
the LivaNova Fabric Development Framework guidelines. This includes data source
registration, scan configuration, business glossary creation, custom classifications,
sensitivity labels, and DLP policies.

The Purview governance API landscape is split between two separate control planes:

1. **Purview Data Governance REST API** — Manages data sources, scans, glossary,
   classifications, and catalog operations. Accessible via Python SDKs
   (`azure-purview-scanning`, `azure-purview-catalog`, `azure-purview-datamap`).

2. **Microsoft Purview Compliance Portal** — Manages sensitivity labels, DLP policies,
   auto-labeling, and information barriers. Only accessible via the compliance
   portal UI or PowerShell (`ExchangeOnlineManagement` module).

## Decision

Use a **hybrid approach**:

- **Python SDK** (`azure-purview-scanning` + `azure-purview-catalog`) for data source
  registration, scan management, business glossary, and custom classifications.
  Scripts in `scripts/governance/` are idempotent and can be re-run safely.

- **Manual runbook** (`documentation/runbooks/purview-governance.md`) with optional
  PowerShell commands for sensitivity labels and DLP policies, which cannot be
  automated via the Data Governance REST API.

- **REST API fallback** for operations not covered by the SDK beta packages, using
  `azure-identity` + `requests` against the Atlas v2 API.

## Alternatives Considered

1. **Full PowerShell automation** — Would cover both data governance and compliance
   portal operations, but would require a separate PowerShell toolchain and is
   less consistent with the project's Python-first approach.

2. **Azure CLI only** — `az purview` commands exist but have limited coverage for
   glossary and classification operations.

3. **Terraform/Bicep only** — Purview infrastructure can be deployed via IaC (already
   done in `infra/modules/purview/main.bicep`), but post-deployment governance
   configuration (glossary, classifications, scans) is not supported by Bicep.

## Consequences

### Positive

- Maximum automation where APIs exist
- Clear documentation where manual steps are required
- Idempotent scripts — safe to re-run
- Follows existing project patterns (Python, `DefaultAzureCredential`)

### Negative

- SDK packages are beta (`1.0.0b2`/`b4`) — API surface may change
- Two-track approach (SDK + portal) requires maintaining both

### Mitigation

- Pin SDK versions in `requirements.txt`
- Wrap API calls in helper functions that can be updated independently
- Include PowerShell alternatives in the runbook for portal operations
