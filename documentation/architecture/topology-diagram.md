# Azure Data Platform - Infrastructure Topology

> **Last updated:** 2026-03-01 | **Environment:** Dev deployed | QA/Prod planned

---

## High-Level Platform View

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        AZURE TENANT: mhktechinc.com                            │
│                    (f1430cad-23d4-4001-aa9e-60345970c80e)                       │
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                     MANAGEMENT GROUP HIERARCHY                            │  │
│  │                                                                           │  │
│  │                      Tenant Root Group                                    │  │
│  │                      ┌──────┴──────┐                                      │  │
│  │                MG-Platform    MG-Workloads                                │  │
│  │                    │          ┌─────┴──────┐                              │  │
│  │              Sub-Platform  MG-DataPlatform  MG-Applications               │  │
│  │              (future)      ┌──────┴──────┐     (future)                   │  │
│  │                     Sub-NonProd     Sub-Prod                              │  │
│  │                     (Dev + QA)      (Prod)                                │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │  SUBSCRIPTION: Sub-DataPlatform-Dev                                       │  │
│  │  (9d9e6de8-899f-4fbe-8e31-4925d1356457)                                  │  │
│  │                                                                           │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  RESOURCE GROUP: dp-rg-dev  (East US 2)                            │  │  │
│  │  │                                                                     │  │  │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │  │  │
│  │  │  │MONITORING│ │NETWORKING│ │ IDENTITY │ │KEY VAULT │              │  │  │
│  │  │  │  ✅ Live │ │  ✅ Live │ │  ✅ Live │ │  ✅ Live │              │  │  │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘              │  │  │
│  │  │                                                                     │  │  │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │  │  │
│  │  │  │ STORAGE  │ │POSTGRESQL│ │  FABRIC  │ │APP SERVC │              │  │  │
│  │  │  │ (ADLS v2)│ │  ✅ Live │ │  ⏸ Skip │ │  ⏸ Skip │              │  │  │
│  │  │  │  ✅ Live │ └──────────┘ └──────────┘ └──────────┘              │  │  │
│  │  │  └──────────┘                                                      │  │  │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                          │  │  │
│  │  │  │AI FOUNDRY│ │ PURVIEW  │ │  PLANE   │                          │  │  │
│  │  │  │  ✅ Live │ │  ✅ Live │ │  ⏸ Skip │                          │  │  │
│  │  │  └──────────┘ └──────────┘ └──────────┘                          │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Network Topology (Hub-Spoke)

```
                              INTERNET
                                 │
                                 │
                    ┌────────────┴────────────┐
                    │                          │
          ┌─────────────────┐       ┌─────────────────┐
          │  HUB VNET        │       │  SPOKE VNET      │
          │  dp-vnet-hub-dev │       │  dp-vnet-spoke-  │
          │  10.0.0.0/16     │       │  dev             │
          │                  │◄─────►│  10.1.0.0/16     │
          │  ┌────────────┐  │ VNET  │                  │
          │  │ Gateway    │  │PEERING│  ┌────────────┐  │
          │  │ Subnet     │  │       │  │snet-fabric │  │
          │  │10.0.0.0/27 │  │       │  │10.1.0.0/24 │  │
          │  └────────────┘  │       │  │NSG: fabric │  │
          │                  │       │  └────────────┘  │
          │  ┌────────────┐  │       │                  │
          │  │ AzFirewall │  │       │  ┌────────────┐  │
          │  │ Subnet     │  │       │  │snet-private│  │
          │  │10.0.1.0/26 │  │       │  │-endpoints  │  │
          │  └────────────┘  │       │  │10.1.1.0/24 │  │
          │                  │       │  │NSG: pe     │  │
          │  ┌────────────┐  │       │  │            │  │
          │  │ Bastion    │  │       │  │ ┌────────┐ │  │
          │  │ Subnet     │  │       │  │ │PE: KV  │ │  │
          │  │10.0.2.0/26 │  │       │  │ │(active)│ │  │
          │  └────────────┘  │       │  │ ├────────┤ │  │
          │                  │       │  │ │PE:Blob │ │  │
          │                  │       │  │ │(active)│ │  │
          │                  │       │  │ ├────────┤ │  │
          │                  │       │  │ │PE:DFS  │ │  │
          │                  │       │  │ │(active)│ │  │
          │                  │       │  │ ├────────┤ │  │
          │                  │       │  │ │PE:Purv.│ │  │
          │                  │       │  │ │Account │ │  │
          │                  │       │  │ │(active)│ │  │
          │                  │       │  │ ├────────┤ │  │
          │                  │       │  │ │PE:Purv.│ │  │
          │                  │       │  │ │Portal  │ │  │
          │                  │       │  │ │(active)│ │  │
          │                  │       │  │ └────────┘ │  │
          │                  │       │  └────────────┘  │
          └──────────────────┘       │                  │
                                     │  ┌────────────┐  │
                                     │  │snet-app-   │  │
                                     │  │service     │  │
                                     │  │10.1.2.0/24 │  │
                                     │  │NSG: appsvc │  │
                                     │  │Delegated to│  │
                                     │  │Web/server  │  │
                                     │  └────────────┘  │
                                     │                  │
                                     │  ┌────────────┐  │
                                     │  │snet-data   │  │
                                     │  │10.1.3.0/24 │  │
                                     │  │NSG: data   │  │
                                     │  │Delegated to│  │
                                     │  │PostgreSQL  │  │
                                     │  └────────────┘  │
                                     │                  │
                                     │  ┌────────────┐  │
                                     │  │snet-self-  │  │
                                     │  │hosted-ir   │  │
                                     │  │10.1.4.0/24 │  │
                                     │  │NSG: shir   │  │
                                     │  └────────────┘  │
                                     │                  │
                                     └──────────────────┘

     ┌──────────────────────────────────────────────────────┐
     │              PRIVATE DNS ZONES (8 zones)             │
     │  All linked to dp-vnet-spoke-dev                     │
     │                                                      │
     │  ● privatelink.vaultcore.azure.net      → Key Vault  │
     │  ● privatelink.blob.core.windows.net   → Blob Store │
     │  ● privatelink.dfs.core.windows.net    → ADLS DFS   │
     │  ● privatelink.postgres.database...     → PostgreSQL │
     │  ● privatelink.azurewebsites.net        → App Svc   │
     │  ● privatelink.purview.azure.com        → Purview   │
     │  ● privatelink.cognitiveservices...     → AI Foundry│
     │  ● privatelink.openai.azure.com         → OpenAI    │
     └──────────────────────────────────────────────────────┘
```

---

## Deployed Resources Detail

```
dp-rg-dev (Resource Group)
│
├── MONITORING ──────────────────────────────────────────────
│   ├── dp-log-dev                    Log Analytics Workspace
│   │   ├── DataPlatformErrors        Saved Query
│   │   ├── PostgreSQLSlowQueries     Saved Query
│   │   └── KeyVaultOperations        Saved Query
│   ├── dp-appi-dev                   Application Insights
│   ├── dp-ag-platform-dev            Action Group
│   └── dp-alert-high-ingestion-dev   Scheduled Query Alert
│
├── NETWORKING ──────────────────────────────────────────────
│   ├── dp-vnet-hub-dev               Hub Virtual Network
│   │   └── peer-hub-to-spoke-dev     VNet Peering → Spoke
│   ├── dp-vnet-spoke-dev             Spoke Virtual Network
│   │   ├── snet-fabric               10.1.0.0/24
│   │   ├── snet-private-endpoints    10.1.1.0/24
│   │   ├── snet-app-service          10.1.2.0/24 (delegated)
│   │   ├── snet-data                 10.1.3.0/24 (delegated)
│   │   ├── snet-self-hosted-ir       10.1.4.0/24
│   │   └── peer-spoke-to-hub-dev     VNet Peering → Hub
│   ├── dp-nsg-fabric-dev             NSG → snet-fabric
│   ├── dp-nsg-pe-dev                 NSG → snet-private-endpoints
│   ├── dp-nsg-appsvc-dev             NSG → snet-app-service
│   ├── dp-nsg-data-dev               NSG → snet-data
│   ├── dp-nsg-shir-dev               NSG → snet-self-hosted-ir
│   └── 6x Private DNS Zones          (with VNet links)
│
├── IDENTITY ────────────────────────────────────────────────
│   ├── dp-id-platform-dev            Managed Identity (admin)
│   │   └── Roles: KV Secrets Officer, Monitoring Publisher
│   ├── dp-id-data-ingestion-dev      Managed Identity (pipelines)
│   │   └── Roles: Blob Data Contributor, KV Secrets User
│   └── dp-id-appsvc-dev              Managed Identity (web apps)
│       └── Roles: KV Secrets User, Cognitive Svc User
│
├── KEY VAULT ───────────────────────────────────────────────
│   ├── dp-kv-dev-dpykeu37cxj6q       Key Vault (RBAC mode)
│   │   ├── Admin: vsingam@mhktechinc.com (KV Administrator)
│   │   ├── Platform ID: KV Secrets Officer
│   │   ├── Public Access: Disabled
│   │   └── Diagnostic Settings → dp-log-dev
│   └── dp-pe-kv-dev                  Private Endpoint
│       └── DNS: privatelink.vaultcore.azure.net
│
├── STORAGE (ADLS Gen2 LAKEHOUSE) ──────────────────────────
│   ├── dpstlakedev*               Storage Account (HNS enabled)
│   │   ├── Container: bronze      Raw data (Parquet)
│   │   │   ├── erp_sap/           SAP SD: vbak, vbap, kna1, mara, mard...
│   │   │   ├── crm_salesforce/    Salesforce: accounts, contacts, opps...
│   │   │   └── iot/telemetry/     IoT sensor readings
│   │   ├── Container: silver      Cleaned, deduped (future)
│   │   ├── Container: gold         Aggregated KPIs, ML predictions
│   │   │   └── equipment_health_scores.parquet
│   │   ├── Container: rag-documents
│   │   │   ├── product-catalog/   JSON + CSV for RAG indexing
│   │   │   ├── customer-360/     Customer 360 Markdown (all 10K)
│   │   │   ├── transactions/     Order lifecycle JSON (~70K)
│   │   │   └── equipment-health/ Equipment health reports (~200)
│   │   ├── Public Access: Enabled (dev), Disabled (prod)
│   │   └── Diagnostic Settings → dp-log-dev
│   ├── dp-pe-blob-dev             Private Endpoint (blob)
│   │   └── DNS: privatelink.blob.core.windows.net
│   └── dp-pe-dfs-dev              Private Endpoint (DFS)
│       └── DNS: privatelink.dfs.core.windows.net
│
├── POSTGRESQL (✅ deployed) ────────────────────────────────
│   ├── dp-psql-dev                 Flexible Server (B1ms)
│   │   ├── Version: 16 + pgvector + uuid-ossp
│   │   ├── Databases: manufacturing_db, sales_db, vector_db
│   │   ├── VNet Integration: snet-data (10.1.3.0/24)
│   │   ├── Private DNS: privatelink.postgres.database.azure.com
│   │   └── Public Access: Disabled
│   └── Tables: equipment_health, iot_telemetry, document_embeddings
│
├── FABRIC (⏸ not deployed) ─────────────────────────────────
│   └── Enable with: enableFabric=true (~$262/mo)
│
├── APP SERVICE (⏸ not deployed) ────────────────────────────
│   └── Enable with: enableAppService=true (~$55/mo)
│
├── AI FOUNDRY (✅ deployed) ────────────────────────────────
│   ├── dp-aih-dev                  AI Hub
│   ├── dp-aip-mfg-sales-dev       AI Project
│   ├── dp-aoai-dev                 Azure OpenAI (S0)
│   │   ├── gpt-4o-equipment-health    (30K TPM)
│   │   └── text-embedding-3-large-rag (50K TPM)
│   ├── dpstaidevdpykeu37cxj6q     AI Storage
│   ├── dpcraidevdpykeu37cxj6q     Container Registry (Premium)
│   └── 3 Private Endpoints (Hub, CR, Storage)
│
├── PURVIEW (DATA GOVERNANCE) ──────────────────────────────
│   ├── dp-pview-dev                 Purview Account
│   │   ├── System-Assigned MI (Storage Blob Data Reader)
│   │   ├── Public Access: Disabled
│   │   ├── Managed RG: dp-rg-pview-managed-dev
│   │   ├── Data Sources: ADLS Gen2 lakehouse, PostgreSQL
│   │   ├── Scan Schedule: Weekly (Sunday 2 AM UTC)
│   │   ├── Business Glossary: 20 terms / 4 categories
│   │   ├── Custom Classifications: 5 rules + 7 built-in SITs
│   │   └── Diagnostic Settings → dp-log-dev
│   ├── dp-pe-pview-account-dev      Private Endpoint (account)
│   │   └── DNS: privatelink.purview.azure.com
│   └── dp-pe-pview-portal-dev       Private Endpoint (portal)
│       └── DNS: privatelink.purview.azure.com
│
└── PLANE TICKETING (⏸ not deployed) ────────────────────────
    └── Enable with: enablePlane=true (~$30/mo)
```

---

## Data Flow Architecture (Target State)

```
  DATA SOURCES               ADLS GEN2 LAKEHOUSE (LIVE)               CONSUMERS
 ─────────────              ──────────────────────────               ──────────

 ┌───────────┐     ┌─────────────────────────────────────────┐    ┌───────────┐
 │ SAP S/4   │────►│           dpstlakedev*                  │    │  Power BI │
 │ (9 tables:│     │  ┌─────────┐  ┌─────────┐  ┌────────┐  │    │  Reports  │
 │ VBAK,VBAP,│     │  │ BRONZE  │  │ SILVER  │  │  GOLD  │  │───►│ (Direct   │
 │ KNA1,MARA,│     │  │         │  │         │  │        │  │    │  Lake)    │
 │ MARD,VBRK,│     │  │Parquet  │  │Cleaned, │  │Star    │  │    └───────────┘
 │ VBRP,LIKP,│     │  │files per│─►│deduped, │─►│schema, │  │
 │ LIPS)     │     │  │source   │  │SCD2,    │  │KPIs,   │  │    ┌───────────┐
 └───────────┘     │  │system   │  │DQ checks│  │ML feat.│  │    │ Streamlit │
                   │  └─────────┘  └─────────┘  └───┬────┘  │    │  Admin    │
 ┌───────────┐     │                                 │       │───►│  Portal   │
 │ Salesforce│────►│  bronze/          bronze/        │       │    └───────────┘
 │ CRM       │     │  erp_sap/         crm_salesforce/│       │
 │ (7 objects:│     │  ├─vbak/          ├─accounts/   │       │    ┌───────────┐
 │ Accounts, │     │  ├─vbap/          ├─contacts/   │       │    │ React     │
 │ Contacts, │     │  ├─kna1/          ├─opportunities│       │───►│ Web App   │
 │ Opps...)  │     │  ├─mara/          ├─leads/      │       │    │ (AI Chat) │
 └───────────┘     │  └─...            └─...         │       │    └───────────┘
                   │                                  │       │
 ┌───────────┐     │  ┌──────────────────────────┐    │       │
 │  IoT      │────►│  │ RAG-DOCUMENTS container  │    │       │
 │  Sensors  │     │  │ product-catalog/ (JSON)   │    │       │
 │ (200 equip│     │  │ customer-360/ (Markdown)  │    │       │
 │  6 types) │     │  │ transactions/ (JSON)      │    │       │
 └───────────┘     │  │ equipment-health/ (MD)    │◄───┘       │
                   │  └──────────────────────────┘    │       │
                   │                                   │       │
                   │  ┌──────────────────────────┐    │       │
                   │  │ ML PIPELINE (local)       │    │       │
                   │  │ IoT → Features → RF Model │    │       │
                   │  │ → Health Scores (gold/)   │    │       │
                   │  │ → Equipment RAG docs      │    │       │
                   │  └──────────────────────────┘    │       │
                   └──────────────────────────────────┘       │
                               ▲                              │
                               │ Scan (MSI auth)              │
                   ┌───────────┴─────────────────────┐        │
                   │  PURVIEW (DATA GOVERNANCE)       │        │
                   │  dp-pview-dev                    │        │
                   │  ┌──────────┐ ┌────────────────┐ │        │
                   │  │Data Map  │ │Business Glossary│ │        │
                   │  │(weekly   │ │(20 terms, SAP/ │ │        │
                   │  │ scans)   │ │ CRM/IoT/Plat.) │ │        │
                   │  └──────────┘ └────────────────┘ │        │
                   │  ┌──────────┐ ┌────────────────┐ │        │
                   │  │PII       │ │Sensitivity     │ │        │
                   │  │Detection │ │Labels + DLP    │ │        │
                   │  │(5 custom │ │(Compliance     │ │        │
                   │  │ + 7 SIT) │ │ Portal)        │ │        │
                   │  └──────────┘ └────────────────┘ │        │
                   └──────────────────────────────────┘        │
                                                              │
                   ┌──────────────────────────────────────────┘
                   │
                   ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                    AI / ML LAYER                            │
 │                                                             │
 │  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
 │  │ Fabric Data │    │  AI Foundry  │    │  PostgreSQL   │  │
 │  │ Agent       │───►│  Agents      │◄──►│  + pgvector   │  │
 │  │             │    │              │    │               │  │
 │  │ Gold layer  │    │ GPT-4.1      │    │ RAG vectors   │  │
 │  │ tables via  │    │ GPT-4o       │    │ Product docs  │  │
 │  │ identity    │    │              │    │ Customer 360  │  │
 │  │ passthrough │    │ Demand Agent │    │ Equip Health  │  │
 │  └─────────────┘    │ Sales Agent  │    │ Hybrid search │  │
 │                     │ Maint. Agent │    │ HNSW indexes  │  │
 │                     └──────────────┘    └───────────────┘  │
 │                     └──────────────┘                        │
 └─────────────────────────────────────────────────────────────┘
```

---

## Application Architecture

```
                         ┌──────────────────┐
                         │   Azure Entra ID │
                         │   (SSO / MSAL)   │
                         └────────┬─────────┘
                                  │ OAuth 2.0
                    ┌─────────────┼─────────────┐
                    │             │             │
                    ▼             ▼             ▼
          ┌─────────────┐ ┌────────────┐ ┌───────────┐
          │  Streamlit   │ │   React    │ │   Slack   │
          │  Admin Portal│ │   Web App  │ │Integration│
          │  (internal)  │ │ (external) │ │ (webhooks)│
          │              │ │            │ │           │
          │ • Dashboard  │ │ • AI Chat  │ │ • Alerts  │
          │ • Pipelines  │ │ • Analytics│ │ • Pipeline│
          │ • AI Agents  │ │ • Support  │ │   notifs  │
          │ • Env Config │ │   (Plane)  │ │ • Incidents│
          └──────┬───────┘ └─────┬──────┘ └─────┬─────┘
                 │               │              │
                 └───────────────┼──────────────┘
                                 │
                                 ▼
                       ┌─────────────────┐
                       │    FastAPI      │
                       │    Backend      │
                       │    /api/v1/     │
                       │                 │
                       │ • /chat (SSE)   │
                       │ • /analytics    │
                       │ • /pipelines    │
                       │ • /tickets      │
                       └────────┬────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  AI Foundry  │  │  Fabric REST │  │  Plane API   │
    │  (agents)    │  │  API (data)  │  │  (tickets)   │
    └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Security & Identity Model

```
┌──────────────────────────────────────────────────────────────┐
│                    ENTRA ID (Azure AD)                        │
│                                                              │
│  Security Groups:                                            │
│  ┌──────────────────────┐  ┌──────────────────────┐         │
│  │ SG-DataPlatform-     │  │ SG-DataEngineers     │         │
│  │ Admins               │  │                      │         │
│  │ → Full admin access  │  │ → Fabric contributor │         │
│  └──────────────────────┘  └──────────────────────┘         │
│  ┌──────────────────────┐  ┌──────────────────────┐         │
│  │ SG-DataScientists-AI │  │ SG-Analysts-ReadOnly │         │
│  │ → AI Foundry + NB    │  │ → Power BI + Gold RO │         │
│  └──────────────────────┘  └──────────────────────┘         │
│                                                              │
│  Managed Identities:                                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ dp-id-platform-dev     → KV Secrets Officer          │   │
│  │                        → Monitoring Metrics Publisher │   │
│  │ dp-id-data-ingestion   → Blob Data Contributor       │   │
│  │                        → KV Secrets User             │   │
│  │ dp-id-appsvc-dev       → KV Secrets User             │   │
│  │                        → Cognitive Services User     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Key Vault Admin:                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ vsingam@mhktechinc.com → Key Vault Administrator     │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## Environment Comparison

```
┌────────────────┬──────────────────┬──────────────────┬──────────────────┐
│    Resource     │       DEV        │        QA        │       PROD       │
├────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ Subscription   │ Sub-DataPlatform │ Sub-DataPlatform │ Sub-DataPlatform │
│                │ -Dev ✅           │ -Dev (shared)    │ -Prod (separate) │
├────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ Hub VNet       │ 10.0.0.0/16 ✅   │ 10.2.0.0/16     │ 10.4.0.0/16     │
│ Spoke VNet     │ 10.1.0.0/16 ✅   │ 10.3.0.0/16     │ 10.5.0.0/16     │
├────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ PostgreSQL     │ B2s (⏸ skip)     │ D2s_v3           │ D4s_v3 + HA     │
│ Fabric         │ F2 (⏸ skip)      │ F4               │ F64             │
│ App Service    │ B2 (⏸ skip)      │ S2               │ P2v3 + slots    │
├────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ Storage(ADLS)  │ ✅ LRS, pub acc  │ ✅ GRS           │ ✅ GRS, no pub  │
│ Key Vault      │ ✅ No purge prot │ ✅ No purge prot │ ✅ Purge protect│
│ Monitoring     │ ✅ 30d retention │ ✅ 30d retention │ ✅ 90d retention│
│ Networking     │ ✅ Hub + Spoke   │ ✅ Hub + Spoke   │ ✅ Hub + Spoke  │
│ Identity       │ ✅ 3 MI + RBAC  │ ✅ 3 MI + RBAC  │ ✅ 3 MI + RBAC │
├────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ Classification │ Internal         │ Confidential     │ Highly Confident.│
│ Est. Cost/mo   │ ~$5-10 (current) │ ~$400-600        │ ~$2,000-3,000   │
└────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

---

## Quick Reference - Enable Resources

```bash
# Current deployment (core + storage + purview, ~$5-20/mo):
az deployment sub create --location eastus2 --template-file infra/main.bicep \
  --parameters environment='dev' keyVaultAdminObjectId='b8f43d7c-...' \
  enableStorage=true enablePurview=true enableFabric=false enableAppService=false \
  enablePostgresql=false enableAIFoundry=false enablePlane=false

# Add PostgreSQL (+~$50/mo):
#   enablePostgresql=true postgresAdminLogin=pgadmin postgresAdminPassword='...'

# Add App Service (+~$55/mo):
#   enableAppService=true

# Add Fabric (+~$262/mo):
#   enableFabric=true fabricAdminMembers='["vsingam@mhktechinc.com"]'

# Add AI Foundry (usage-based):
#   enableAIFoundry=true

# Add Purview (usage-based):
#   enablePurview=true

# Add Plane ticketing (+~$30/mo):
#   enablePlane=true planePostgresPassword='...'

# Upload synthetic data to lakehouse:
#   cd data-platform/synthetic-data
#   python -m venv .venv && source .venv/bin/activate
#   pip install -r requirements.txt
#   python generate_all.py --upload
```
