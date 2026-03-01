# Purview Governance Runbook

> Configuration guide for Microsoft Purview data governance, aligned with the
> LivaNova Fabric Development Framework (Section 5: Data Governance).

## Overview

Microsoft Purview provides unified data governance across the data estate:

| Component | Purpose | Configuration |
|-----------|---------|---------------|
| Data Map | Automated discovery and scanning | `scripts/governance/register_sources.py` + `configure_scans.py` |
| Unified Catalog | Searchable catalog with business glossary | `scripts/governance/create_glossary.py` |
| Classifications | PII detection and custom data classification | `scripts/governance/create_classifications.py` |
| Sensitivity Labels | Information protection labels | Compliance Portal (manual, see Section 3) |
| DLP Policies | Data loss prevention enforcement | Compliance Portal (manual, see Section 4) |
| Lineage | Source-to-report data lineage tracking | Automatic via Fabric/ADF integration |

**Key Principle:** Purview defines policies and metadata; Fabric enforces access and operational security.

## 1. Automated Configuration

### Prerequisites

- Azure CLI authenticated (`az login`)
- Purview account deployed (`dp-pview-dev`)
- Python 3.11+ with governance SDK packages

### Install Dependencies

```bash
cd scripts/governance
pip install -r requirements.txt
```

### Run All Scripts

```bash
python run_all.py
```

Or run individually:

```bash
# Step 1: Register ADLS Gen2 and PostgreSQL as data sources
python register_sources.py

# Step 2: Configure scan rule set, scan, weekly schedule, and run initial scan
python configure_scans.py --run-now

# Step 3: Create business glossary (4 categories, 20 terms)
python create_glossary.py

# Step 4: Create custom classification rules (5 custom + 7 built-in SITs)
python create_classifications.py

# Step 5: Verify all configuration
python verify_governance.py
```

### Data Sources Registered

| Source | Name in Purview | Auth | Scan Schedule |
|--------|----------------|------|---------------|
| ADLS Gen2 Lakehouse | `adls-lakehouse-dev` | Managed Identity | Weekly (Sunday 2 AM UTC) |
| PostgreSQL (pgvector) | `postgresql-vector-dev` | Managed Identity | Weekly (Sunday 2 AM UTC) |

### Business Glossary Categories

| Category | Terms | Examples |
|----------|-------|---------|
| SAP ERP | 9 | Customer Number (KUNNR), Material Number (MATNR), Net Value (NETWR) |
| Salesforce CRM | 4 | Account, Contact (PII), Opportunity, Lead (PII) |
| IoT Telemetry | 3 | Equipment Health Score, IoT Telemetry, Failure Risk |
| Data Platform | 4 | Medallion Layer, Active Customer, Revenue, Customer 360 |

### Custom Classifications

| Classification | Description | Column Patterns |
|---------------|-------------|----------------|
| `CUSTOM_CUSTOMER_DATA` | Customer PII (GDPR) | name1, email, smtp_addr, phone, telf1, stras, address |
| `CUSTOM_FINANCIAL_DATA` | Financial data (SOX) | netwr, amount, revenue, price, waerk, currency |
| `CUSTOM_EMPLOYEE_DATA` | Employee data | employee, salary, compensation |
| `CUSTOM_MANUFACTURING_IP` | Trade secrets | recipe, formula, specification, tolerance |
| `CUSTOM_REGULATORY_DATA` | Regulated data (FDA/SEC) | batch_number, serial_number, quality_check |

Built-in SITs enabled: Credit Card, SSN, Email, Phone, Driver's License, Passport, Medical Record Number.

## 2. Governance Roles

| Role | Responsibility | Identity |
|------|---------------|----------|
| Data Curator | Manage catalog, approve access | `dp-id-platform-dev` (Managed Identity) |
| Data Source Admin | Register sources, configure scans | `dp-id-platform-dev` (Managed Identity) |
| Data Steward | Manage glossary, review classifications | Team members (Entra ID) |
| Compliance Officer | Manage sensitivity labels, DLP | Entra ID user (Compliance Admin role) |

## 3. Sensitivity Labels (Manual Configuration)

> Sensitivity labels must be configured in the Microsoft Purview Compliance Portal
> (`compliance.microsoft.com`). They cannot be created via the Data Governance REST API.

### Label Taxonomy

| Label | Priority | Auto-Apply Trigger | Protection |
|-------|----------|-------------------|------------|
| Public | 0 | None | No protection |
| General | 1 | IoT telemetry, equipment data | Header/footer watermark |
| Confidential | 2 | PII detected (email, phone, address) | Encryption, restricted sharing |
| Highly Confidential | 3 | Financial data (credit cards, bank accounts) | Encryption, DLP enforcement, audit logging |
| Restricted | 4 | Manual assignment only | Encryption, CLS/RLS, geographic restrictions |

### Portal Configuration Steps

1. Navigate to `compliance.microsoft.com` > **Information Protection** > **Labels**
2. Create each label from the table above with:
   - Name and description
   - Scope: Items, Files, Emails
   - Protection settings: Encryption, watermarking, access control as specified
3. Click **Publish labels** and create a label policy:
   - Name: `DataPlatformLabelPolicy`
   - Publish to: All users
   - Default label: General
4. Wait 24 hours for sync to Fabric and Purview Data Map
5. In Purview Governance Portal > **Data Map** > **Sensitivity labels**:
   - Consent to extend M365 sensitivity labels to Data Map assets
   - Verify labels appear in scan results

### Optional PowerShell Automation

```powershell
# Requires: Install-Module ExchangeOnlineManagement
Connect-IPPSSession

New-Label -Name "Public" -DisplayName "Public" -Tooltip "Non-confidential data" -Priority 0
New-Label -Name "General" -DisplayName "General" -Tooltip "Internal use, not sensitive" -Priority 1
New-Label -Name "Confidential" -DisplayName "Confidential" -Tooltip "Sensitive internal information" -Priority 2 -EncryptionEnabled $true
New-Label -Name "HighlyConfidential" -DisplayName "Highly Confidential" -Tooltip "Critical business information" -Priority 3 -EncryptionEnabled $true
New-Label -Name "Restricted" -DisplayName "Restricted" -Tooltip "PII, regulated data" -Priority 4 -EncryptionEnabled $true

New-LabelPolicy -Name "DataPlatformLabelPolicy" `
  -Labels "Public","General","Confidential","HighlyConfidential","Restricted" `
  -ExchangeLocation "All"
```

### Auto-Labeling Policies

Configure auto-labeling in the Compliance Portal:

| Policy | Condition | Label Applied |
|--------|-----------|--------------|
| PII Auto-Label | SSN, email, phone, or address detected | Confidential |
| Financial Auto-Label | Credit card or bank account detected | Highly Confidential |

Steps:
1. Go to **Information Protection** > **Auto-labeling**
2. Create policy with conditions from the table
3. Select target locations (SharePoint, OneDrive, Exchange)
4. Start in simulation mode, review results, then enable

## 4. DLP Policies (Manual Configuration)

> DLP policies must be configured in the Microsoft Purview Compliance Portal.

### Policy Definitions

| Policy Name | Condition | Action | Scope |
|-------------|-----------|--------|-------|
| Block PII Export | SSN, email, phone, or address detected in externally shared file | Block sharing, notify admin | ADLS Gen2, SharePoint |
| Alert Financial Data Share | Data labeled "Highly Confidential" shared outside organization | Alert compliance team, allow but log | All M365 workloads |
| Enforce Encryption on Financial | Credit card or bank account detected | Require Confidential+ label | Exchange, SharePoint, OneDrive |
| Customer Data Protection | CUSTOM_CUSTOMER_DATA classification detected | Restrict external sharing, audit all access | ADLS Gen2, SharePoint |

### Configuration Steps

1. Navigate to `compliance.microsoft.com` > **Data loss prevention** > **Policies**
2. Click **Create policy**
3. For each policy in the table above:
   a. Select **Microsoft Fabric** and other locations as scope
   b. Define conditions (sensitivity label, content type, classification)
   c. Configure actions: Block/Allow + Notify/Alert
4. **Deploy in Test mode** for 2 weeks
5. Review alerts in **DLP Activity Explorer**
6. Tune false positives and adjust thresholds
7. Switch to **Enforce** mode

### Optional PowerShell

```powershell
Connect-IPPSSession

New-DlpCompliancePolicy -Name "Block PII Export" `
  -SharePointLocation "All" `
  -OneDriveLocation "All" `
  -Mode "Enable"

New-DlpComplianceRule -Name "Block SSN Export" `
  -Policy "Block PII Export" `
  -ContentContainsSensitiveInformation @{Name="U.S. Social Security Number (SSN)"; MinCount=1} `
  -BlockAccess $true `
  -NotifyUser "SiteAdmin" `
  -GenerateAlert "High"
```

## 5. Governance Rhythm

| Frequency | Activity | Owner |
|-----------|----------|-------|
| Weekly | Review scan results, check for new PII detections | Data Steward |
| Monthly | Review classification accuracy, tune false positives | Data Steward |
| Quarterly | Update business glossary terms, review access requests | Data Steward + Business Owners |
| Annually | Review sensitivity label policies, conduct security assessment | Compliance Officer |

### Weekly Scan Checklist

- [ ] Verify weekly scan completed (Sunday 2 AM UTC)
- [ ] Review newly classified assets in Purview Data Map
- [ ] Check DLP alerts for any policy violations
- [ ] Validate no new PII in non-production environments

## 6. Troubleshooting

### Scan Fails with Authentication Error

The Purview managed identity needs `Storage Blob Data Reader` on the ADLS Gen2 account.
This is configured via `infra/modules/purview/main.bicep` RBAC assignments.

```bash
# Verify Purview MI has storage access
az role assignment list \
  --scope "/subscriptions/<SUB_ID>/resourceGroups/dp-rg-dev" \
  --query "[?roleDefinitionName=='Storage Blob Data Reader']" -o table
```

### Private Endpoint Connection Issues

Purview is deployed with public access disabled. SDK/API calls must route through
the private endpoint or from an Azure-connected network.

```bash
# Verify private endpoints
az network private-endpoint list \
  --resource-group dp-rg-dev \
  --query "[?contains(name, 'pview')].[name, customDnsConfigs[0].fqdn]" -o table
```

### Classification Rules Not Applied

Classification rules are applied during scans, not retroactively. After creating
new rules, re-run a scan:

```bash
cd scripts/governance
python configure_scans.py --run-now
```

### SDK Authentication from Local Machine

If running scripts locally and getting authentication errors:

```bash
# Ensure Azure CLI is logged in
az login

# Verify the correct subscription
az account show --query "{name:name, id:id}" -o table

# Set the subscription if needed
az account set --subscription "Sub-DataPlatform-NonProd"
```

## 7. Maturity Model Checklist

Progress through the LivaNova Purview maturity model:

- [x] Connect 2-3 High-Value Sources (ADLS Gen2 lakehouse, PostgreSQL)
- [x] Deploy Business Glossary and Custom Classifications
- [ ] Apply Sensitivity Labels and Train Users
- [ ] Implement DLP Enforcement
- [ ] Enable Self-Service Data Access (access request workflows)
- [ ] Use Lineage for All Production Reports
- [ ] Establish Governance Rhythm (weekly/monthly/quarterly reviews)
