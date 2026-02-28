# Azure Data Platform - Infrastructure Topology

> **Last updated:** 2026-02-28 | **Environment:** Dev deployed | QA/Prod planned

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
│  │  │  │POSTGRESQL│ │  FABRIC  │ │APP SERVC │ │AI FOUNDRY│              │  │  │
│  │  │  │ ⏸ Skip  │ │  ⏸ Skip │ │  ⏸ Skip │ │  ⏸ Skip │              │  │  │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘              │  │  │
│  │  │                                                                     │  │  │
│  │  │  ┌──────────┐ ┌──────────┐                                        │  │  │
│  │  │  │ PURVIEW  │ │  PLANE   │                                        │  │  │
│  │  │  │ ⏸ Skip  │ │  ⏸ Skip │                                        │  │  │
│  │  │  └──────────┘ └──────────┘                                        │  │  │
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
          │  └────────────┘  │       │  │ └────────┘ │  │
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
     │              PRIVATE DNS ZONES (6 zones)             │
     │  All linked to dp-vnet-spoke-dev                     │
     │                                                      │
     │  ● privatelink.vaultcore.azure.net      → Key Vault  │
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
├── POSTGRESQL (⏸ not deployed) ─────────────────────────────
│   └── Enable with: enablePostgresql=true (~$50/mo)
│
├── FABRIC (⏸ not deployed) ─────────────────────────────────
│   └── Enable with: enableFabric=true (~$262/mo)
│
├── APP SERVICE (⏸ not deployed) ────────────────────────────
│   └── Enable with: enableAppService=true (~$55/mo)
│
├── AI FOUNDRY (⏸ not deployed) ─────────────────────────────
│   └── Enable with: enableAIFoundry=true (usage-based)
│
├── PURVIEW (⏸ not deployed) ────────────────────────────────
│   └── Enable with: enablePurview=true (usage-based)
│
└── PLANE TICKETING (⏸ not deployed) ────────────────────────
    └── Enable with: enablePlane=true (~$30/mo)
```

---

## Data Flow Architecture (Target State)

```
  DATA SOURCES                    FABRIC LAKEHOUSE                    CONSUMERS
 ─────────────                   ─────────────────                   ──────────

 ┌───────────┐     ┌─────────────────────────────────────────┐    ┌───────────┐
 │  SAP/ERP  │────►│                                         │    │  Power BI │
 │  (Sales,  │     │  ┌─────────┐  ┌─────────┐  ┌────────┐  │    │  Reports  │
 │  Inventory)│     │  │ BRONZE  │  │ SILVER  │  │  GOLD  │  │───►│ (Direct   │
 └───────────┘     │  │         │  │         │  │        │  │    │  Lake)    │
                   │  │Raw data,│  │Cleaned, │  │Star    │  │    └───────────┘
 ┌───────────┐     │  │schema on│─►│deduped, │─►│schema, │  │
 │  CRM /    │────►│  │read,    │  │SCD2,    │  │KPIs,   │  │    ┌───────────┐
 │  Dynamics │     │  │audit log│  │DQ checks│  │ML feat.│  │    │ Streamlit │
 └───────────┘     │  └─────────┘  └─────────┘  └───┬────┘  │    │  Admin    │
                   │                                 │       │───►│  Portal   │
 ┌───────────┐     │                                 │       │    └───────────┘
 │  IoT      │────►│  Bronze Tables:    Silver:      │       │
 │  Sensors  │     │  raw_sales_orders  cleaned_     │       │    ┌───────────┐
 └───────────┘     │  raw_inventory     sales_orders │       │    │ React     │
                   │  raw_iot_telemetry cleaned_     │       │───►│ Web App   │
 ┌───────────┐     │  raw_customers     inventory    │       │    │ (AI Chat) │
 │  POS      │────►│                    cleaned_     │       │    └───────────┘
 │  Systems  │     │                    customers    │       │
 └───────────┘     └─────────────────────────────────┘       │
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
 │  │ identity    │    │              │    │ Hybrid search │  │
 │  │ passthrough │    │ Demand Agent │    │ HNSW indexes  │  │
 │  └─────────────┘    │ Sales Agent  │    └───────────────┘  │
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
│ Key Vault      │ ✅ No purge prot │ ✅ No purge prot │ ✅ Purge protect│
│ Monitoring     │ ✅ 30d retention │ ✅ 30d retention │ ✅ 90d retention│
│ Networking     │ ✅ Hub + Spoke   │ ✅ Hub + Spoke   │ ✅ Hub + Spoke  │
│ Identity       │ ✅ 3 MI + RBAC  │ ✅ 3 MI + RBAC  │ ✅ 3 MI + RBAC  │
├────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ Classification │ Internal         │ Confidential     │ Highly Confident.│
│ Est. Cost/mo   │ ~$5-10 (current) │ ~$400-600        │ ~$2,000-3,000   │
└────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

---

## Quick Reference - Enable Resources

```bash
# Current deployment (core only, ~$5-10/mo):
az deployment sub create --location eastus2 --template-file infra/main.bicep \
  --parameters environment='dev' keyVaultAdminObjectId='b8f43d7c-...' \
  enableFabric=false enableAppService=false enablePostgresql=false \
  enablePurview=false enableAIFoundry=false enablePlane=false

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
```
