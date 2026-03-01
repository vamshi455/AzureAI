# Source Systems Data Model Reference

## Table of Contents

- [Overview](#overview)
- [SAP S/4HANA SD (Sales & Distribution)](#sap-s4hana-sd-sales--distribution)
- [Salesforce CRM](#salesforce-crm)
- [Cross-System Linkages](#cross-system-linkages)
- [Data Lake Folder Structure](#data-lake-folder-structure)
- [RAG Document Structure](#rag-document-structure)
- [IoT Telemetry](#iot-telemetry)
- [Predictive Maintenance ML Pipeline](#predictive-maintenance-ml-pipeline)

---

## Overview

The data platform ingests data from **two primary source systems**:

| Source System | Domain | Protocol | Primary Use |
|---------------|--------|----------|-------------|
| **SAP S/4HANA SD** | ERP -- Sales & Distribution | OData / RFC / BAPI | Orders, billing, delivery, material and customer master data |
| **Salesforce CRM** | Customer Relationship Management | REST API (Bulk API 2.0) | Accounts, contacts, opportunities, leads, cases, products |

Both systems feed into the Bronze layer of the Medallion architecture (Fabric Lakehouse)
as raw Parquet files. Cross-system linkage is achieved through shared identifiers mapped
during the Silver layer transformation.

---

## SAP S/4HANA SD (Sales & Distribution)

### Entity Summary

| SAP Table | Entity Name | Description | Estimated Volume | Load Pattern |
|-----------|-------------|-------------|-----------------|--------------|
| `KNA1` | Customer Master | General customer master data | 10,000 rows | Full load (daily) |
| `MARA` | Material Master | General material data | 2,000 rows | Full load (daily) |
| `MARD` | Plant Stock | Material stock at plant/storage location level | 6,000 rows | Full load (daily) |
| `VBAK` | Sales Order Header | Sales document header data | 100,000 rows | Incremental (hourly) |
| `VBAP` | Sales Order Item | Sales document item data | 300,000 rows | Incremental (hourly) |
| `VBRK` | Billing Header | Billing document header data | 80,000 rows | Incremental (hourly) |
| `VBRP` | Billing Item | Billing document item data | 240,000 rows | Incremental (hourly) |
| `LIKP` | Delivery Header | Delivery document header data | 85,000 rows | Incremental (hourly) |
| `LIPS` | Delivery Item | Delivery document item data | 255,000 rows | Incremental (hourly) |

### KNA1 -- Customer Master

Central customer master table holding name, address, and organizational data for all
business partners classified as customers.

**Key Relationships:**
- Referenced by `VBAK.KUNNR` (sold-to party on sales orders)
- Referenced by `VBRK.KUNAG` (payer on billing documents)
- Referenced by `LIKP.KUNNR` (ship-to party on deliveries)
- Linked to Salesforce `Account` via cross-system mapping

**Watermark Column:** `ERDAT` / `AEDAT` (creation/change date)

**Bronze Layer Path:** `bronze/erp_sap/kna1/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `KUNNR` | CHAR(10) | Customer number (primary key) | `0000001234` |
| `NAME1` | CHAR(35) | Customer name | `Acme Manufacturing Inc` |
| `STRAS` | CHAR(35) | Street address | `1200 Industrial Pkwy` |
| `ORT01` | CHAR(35) | City | `Detroit` |
| `REGIO` | CHAR(3) | State / region code | `MI` |
| `PSTLZ` | CHAR(10) | Postal code | `48201` |
| `LAND1` | CHAR(3) | Country key | `US` |
| `TELF1` | CHAR(16) | Phone number | `+1-313-555-0100` |
| `SMTP_ADDR` | CHAR(241) | Email address | `orders@acme-mfg.com` |
| `BRSCH` | CHAR(4) | Industry code | `0003` |
| `VKORG` | CHAR(4) | Sales organization | `1000` |
| `VTWEG` | CHAR(2) | Distribution channel | `10` |
| `SPART` | CHAR(2) | Division | `01` |
| `ERDAT` | DATS | Created on date | `20220315` |
| `AEDAT` | DATS | Last changed date | `20250601` |

### MARA -- Material Master

General material master data holding product descriptions, types, and unit-of-measure
information for all materials managed in the SAP system.

**Key Relationships:**
- Referenced by `VBAP.MATNR` (material on order items)
- Referenced by `VBRP.MATNR` (material on billing items)
- Referenced by `LIPS.MATNR` (material on delivery items)
- Referenced by `MARD.MATNR` (stock records)
- Linked to Salesforce `Product2.ProductCode`

**Watermark Column:** `ERSDA` / `LAEDA` (creation/change date)

**Bronze Layer Path:** `bronze/erp_sap/mara/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `MATNR` | CHAR(18) | Material number (primary key) | `0000000001` |
| `MAKTX` | CHAR(40) | Material description (short text) | `Carbon Steel Coil HR 2.0mm` |
| `MTART` | CHAR(4) | Material type | `ROH` |
| `MATKL` | CHAR(9) | Material group | `001` |
| `MEINS` | CHAR(3) | Base unit of measure | `KG` |
| `BRGEW` | DEC(13,3) | Gross weight | `125.50` |
| `GEWEI` | CHAR(3) | Weight unit | `KG` |
| `ERSDA` | DATS | Created on date | `20230101` |
| `LAEDA` | DATS | Last changed date | `20250415` |

### MARD -- Plant Stock

Stores inventory quantities at the plant and storage location level for each material.

**Key Relationships:**
- `MARD.MATNR` -> `MARA.MATNR`
- Plant code references organizational data

**Watermark Column:** `LFGJA` / `LFMON` (last goods movement year/month)

**Bronze Layer Path:** `bronze/erp_sap/mard/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `MATNR` | CHAR(18) | Material number | `0000000001` |
| `WERKS` | CHAR(4) | Plant code | `1100` |
| `LGORT` | CHAR(4) | Storage location | `0001` |
| `LABST` | DEC(13,3) | Unrestricted-use stock | `2500.000` |
| `INSME` | DEC(13,3) | Stock in quality inspection | `150.000` |
| `SPEME` | DEC(13,3) | Blocked stock | `25.000` |
| `LFGJA` | NUMC(4) | Year of last goods movement | `2025` |
| `LFMON` | NUMC(2) | Month of last goods movement | `11` |

### VBAK -- Sales Order Header

Header-level data for sales orders, including customer, dates, order type, and currency.

**Key Relationships:**
- `VBAK.KUNNR` -> `KNA1.KUNNR`
- `VBAK.VBELN` <- `VBAP.VBELN` (one-to-many)
- `VBAK.VBELN` may reference `VBRK` / `LIKP` via document flow

**Watermark Column:** `ERDAT` / `AEDAT`

**Bronze Layer Path:** `bronze/erp_sap/vbak/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `VBELN` | CHAR(10) | Sales document number (primary key) | `0000012345` |
| `AUART` | CHAR(4) | Sales document type | `ZOR` |
| `VKORG` | CHAR(4) | Sales organization | `1000` |
| `VTWEG` | CHAR(2) | Distribution channel | `10` |
| `SPART` | CHAR(2) | Division | `01` |
| `KUNNR` | CHAR(10) | Sold-to party (customer number) | `0000001234` |
| `ERDAT` | DATS | Created on date | `20250601` |
| `ERZET` | TIMS | Created at time | `143025` |
| `AUDAT` | DATS | Document date | `20250601` |
| `VDATU` | DATS | Requested delivery date | `20250615` |
| `WAERK` | CHAR(5) | SD document currency | `USD` |
| `NETWR` | DEC(15,2) | Net value of order | `24850.00` |
| `BSTNK` | CHAR(20) | Customer purchase order number | `PO-2025-0042` |

### VBAP -- Sales Order Item

Line-item detail for sales orders, including material, quantity, pricing, and plant assignment.

**Key Relationships:**
- `VBAP.VBELN` -> `VBAK.VBELN`
- `VBAP.MATNR` -> `MARA.MATNR`

**Watermark Column:** `ERDAT` / `AEDAT`

**Bronze Layer Path:** `bronze/erp_sap/vbap/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `VBELN` | CHAR(10) | Sales document number | `0000012345` |
| `POSNR` | NUMC(6) | Item number (within document) | `000010` |
| `MATNR` | CHAR(18) | Material number | `0000000001` |
| `KWMENG` | DEC(15,3) | Order quantity | `500.000` |
| `VRKME` | CHAR(3) | Sales unit | `KG` |
| `NETWR` | DEC(15,2) | Net value of item | `425.00` |
| `WAERK` | CHAR(5) | Currency | `USD` |
| `WERKS` | CHAR(4) | Plant | `1100` |
| `LGORT` | CHAR(4) | Storage location | `0001` |
| `ERDAT` | DATS | Created on date | `20250601` |
| `AEDAT` | DATS | Last changed date | `20250602` |

### VBRK -- Billing Header

Header-level billing (invoice) data, linked to sales orders via SAP document flow.

**Key Relationships:**
- `VBRK.KUNAG` -> `KNA1.KUNNR` (payer)
- `VBRK.VBELN` <- `VBRP.VBELN` (one-to-many)

**Watermark Column:** `ERDAT`

**Bronze Layer Path:** `bronze/erp_sap/vbrk/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `VBELN` | CHAR(10) | Billing document number (primary key) | `0000098765` |
| `FKART` | CHAR(4) | Billing type | `F2` |
| `FKDAT` | DATS | Billing date | `20250610` |
| `KUNAG` | CHAR(10) | Payer (customer number) | `0000001234` |
| `WAERK` | CHAR(5) | Currency | `USD` |
| `NETWR` | DEC(15,2) | Net value | `24850.00` |
| `ERDAT` | DATS | Created on date | `20250610` |

### VBRP -- Billing Item

Line-item detail for billing documents.

**Key Relationships:**
- `VBRP.VBELN` -> `VBRK.VBELN`
- `VBRP.MATNR` -> `MARA.MATNR`
- `VBRP.AUBEL` -> `VBAK.VBELN` (reference sales order)

**Watermark Column:** `ERDAT`

**Bronze Layer Path:** `bronze/erp_sap/vbrp/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `VBELN` | CHAR(10) | Billing document number | `0000098765` |
| `POSNR` | NUMC(6) | Item number | `000010` |
| `MATNR` | CHAR(18) | Material number | `0000000001` |
| `FKIMG` | DEC(13,3) | Billed quantity | `500.000` |
| `VRKME` | CHAR(3) | Sales unit | `KG` |
| `NETWR` | DEC(15,2) | Net value | `425.00` |
| `WAERK` | CHAR(5) | Currency | `USD` |
| `AUBEL` | CHAR(10) | Reference sales order number | `0000012345` |
| `ERDAT` | DATS | Created on date | `20250610` |

### LIKP -- Delivery Header

Header data for outbound deliveries.

**Key Relationships:**
- `LIKP.KUNNR` -> `KNA1.KUNNR` (ship-to party)
- `LIKP.VBELN` <- `LIPS.VBELN` (one-to-many)

**Watermark Column:** `ERDAT`

**Bronze Layer Path:** `bronze/erp_sap/likp/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `VBELN` | CHAR(10) | Delivery document number (primary key) | `0000054321` |
| `LFART` | CHAR(4) | Delivery type | `LF` |
| `KUNNR` | CHAR(10) | Ship-to party (customer number) | `0000001234` |
| `WADAT` | DATS | Planned goods movement date | `20250612` |
| `WADAT_IST` | DATS | Actual goods movement date | `20250613` |
| `VSTEL` | CHAR(4) | Shipping point | `1100` |
| `ERDAT` | DATS | Created on date | `20250608` |

### LIPS -- Delivery Item

Line-item detail for delivery documents.

**Key Relationships:**
- `LIPS.VBELN` -> `LIKP.VBELN`
- `LIPS.MATNR` -> `MARA.MATNR`
- `LIPS.VGBEL` -> `VBAK.VBELN` (reference sales order)

**Watermark Column:** `ERDAT`

**Bronze Layer Path:** `bronze/erp_sap/lips/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `VBELN` | CHAR(10) | Delivery document number | `0000054321` |
| `POSNR` | NUMC(6) | Item number | `000010` |
| `MATNR` | CHAR(18) | Material number | `0000000001` |
| `LFIMG` | DEC(13,3) | Delivered quantity | `500.000` |
| `VRKME` | CHAR(3) | Sales unit | `KG` |
| `WERKS` | CHAR(4) | Plant | `1100` |
| `LGORT` | CHAR(4) | Storage location | `0001` |
| `VGBEL` | CHAR(10) | Reference sales order number | `0000012345` |
| `ERDAT` | DATS | Created on date | `20250608` |

---

## Salesforce CRM

### Entity Summary

| API Object Name | Entity Name | Description | Estimated Volume | Load Pattern |
|-----------------|-------------|-------------|-----------------|--------------|
| `Account` | Accounts | Company/customer records | 10,000 rows | Incremental (`SystemModstamp`) |
| `Contact` | Contacts | Individual contacts at accounts | 30,000 rows | Incremental (`SystemModstamp`) |
| `Opportunity` | Opportunities | Sales deals and pipeline | 50,000 rows | Incremental (`SystemModstamp`) |
| `Lead` | Leads | Prospective customers | 40,000 rows | Incremental (`SystemModstamp`) |
| `Case` | Cases | Support cases and issues | 25,000 rows | Incremental (`SystemModstamp`) |
| `Product2` | Products | Product catalog entries | 2,000 rows | Full load (daily) |
| `PricebookEntry` | Pricebook Entries | Product pricing records | 6,000 rows | Full load (daily) |

### Account

Core customer/company entity in Salesforce. Each Account maps to one SAP customer
master record (KNA1) via the custom `sap_customer_number__c` field.

**Key Relationships:**
- `Account.Id` <- `Contact.AccountId` (one-to-many)
- `Account.Id` <- `Opportunity.AccountId` (one-to-many)
- `Account.Id` <- `Case.AccountId` (one-to-many)
- `Account.sap_customer_number__c` -> `KNA1.KUNNR` (cross-system link)

**Watermark Column:** `SystemModstamp`

**Bronze Layer Path:** `bronze/crm_salesforce/accounts/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `Id` | ID(18) | Salesforce record ID (primary key) | `001Dn00000A1b2cXYZ` |
| `Name` | String(255) | Account name | `Acme Manufacturing Inc` |
| `Industry` | Picklist | Industry classification | `Manufacturing` |
| `BillingStreet` | String(255) | Billing street address | `1200 Industrial Pkwy` |
| `BillingCity` | String(40) | Billing city | `Detroit` |
| `BillingState` | String(80) | Billing state/province | `MI` |
| `BillingPostalCode` | String(20) | Billing postal code | `48201` |
| `BillingCountry` | String(80) | Billing country | `US` |
| `Phone` | Phone | Main phone number | `+1-313-555-0100` |
| `Website` | URL | Company website | `https://www.acme-mfg.com` |
| `AnnualRevenue` | Currency | Annual revenue | `12500000.00` |
| `NumberOfEmployees` | Integer | Employee count | `450` |
| `sap_customer_number__c` | String(10) | SAP KUNNR (cross-system key) | `0000001234` |
| `CreatedDate` | DateTime | Record creation timestamp | `2022-03-15T10:30:00Z` |
| `SystemModstamp` | DateTime | Last modified timestamp (watermark) | `2025-06-01T14:30:25Z` |

### Contact

Individual persons associated with an Account.

**Key Relationships:**
- `Contact.AccountId` -> `Account.Id`

**Watermark Column:** `SystemModstamp`

**Bronze Layer Path:** `bronze/crm_salesforce/contacts/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `Id` | ID(18) | Salesforce record ID (primary key) | `003Dn00000B2c3dXYZ` |
| `AccountId` | Reference(Account) | Parent account ID | `001Dn00000A1b2cXYZ` |
| `FirstName` | String(40) | First name | `Jane` |
| `LastName` | String(80) | Last name | `Smith` |
| `Title` | String(128) | Job title | `Procurement Manager` |
| `Email` | Email | Email address | `jsmith@acme-mfg.com` |
| `Phone` | Phone | Phone number | `+1-313-555-0101` |
| `Department` | String(80) | Department | `Purchasing` |
| `MailingCity` | String(40) | City | `Detroit` |
| `MailingState` | String(80) | State | `MI` |
| `MailingCountry` | String(80) | Country | `US` |
| `CreatedDate` | DateTime | Record creation timestamp | `2022-04-10T09:15:00Z` |
| `SystemModstamp` | DateTime | Last modified timestamp | `2025-05-20T11:45:30Z` |

### Opportunity

Sales deals tracked through the pipeline from prospecting to close.

**Key Relationships:**
- `Opportunity.AccountId` -> `Account.Id`
- Opportunities in "Closed Won" stage may reference SAP sales orders via custom field

**Watermark Column:** `SystemModstamp`

**Bronze Layer Path:** `bronze/crm_salesforce/opportunities/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `Id` | ID(18) | Salesforce record ID (primary key) | `006Dn00000C3d4eXYZ` |
| `AccountId` | Reference(Account) | Associated account | `001Dn00000A1b2cXYZ` |
| `Name` | String(120) | Opportunity name | `Acme Q3 Bearing Order` |
| `StageName` | Picklist | Pipeline stage | `Negotiation` |
| `Amount` | Currency | Deal amount | `48500.00` |
| `CloseDate` | Date | Expected close date | `2025-07-15` |
| `Probability` | Percent | Win probability | `60` |
| `LeadSource` | Picklist | Lead source | `Trade Show` |
| `Type` | Picklist | Opportunity type | `New Business` |
| `sap_order_number__c` | String(10) | SAP VBELN (post-close) | `0000012345` |
| `CreatedDate` | DateTime | Record creation timestamp | `2025-04-01T08:00:00Z` |
| `SystemModstamp` | DateTime | Last modified timestamp | `2025-06-02T16:20:00Z` |

### Lead

Prospective customers not yet converted to Accounts/Contacts/Opportunities.

**Key Relationships:**
- Converted leads create `Account`, `Contact`, and `Opportunity` records

**Watermark Column:** `SystemModstamp`

**Bronze Layer Path:** `bronze/crm_salesforce/leads/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `Id` | ID(18) | Salesforce record ID (primary key) | `00QDn00000D4e5fXYZ` |
| `FirstName` | String(40) | First name | `Robert` |
| `LastName` | String(80) | Last name | `Johnson` |
| `Company` | String(255) | Company name | `Delta Hydraulics LLC` |
| `Title` | String(128) | Job title | `Plant Manager` |
| `Email` | Email | Email address | `rjohnson@deltahydraulics.com` |
| `Phone` | Phone | Phone number | `+1-614-555-0200` |
| `Industry` | Picklist | Industry | `Manufacturing` |
| `LeadSource` | Picklist | Originating source | `Web` |
| `Status` | Picklist | Lead status | `Working - Contacted` |
| `Rating` | Picklist | Lead quality rating | `Hot` |
| `AnnualRevenue` | Currency | Estimated annual revenue | `5000000.00` |
| `IsConverted` | Boolean | Whether lead has been converted | `false` |
| `CreatedDate` | DateTime | Record creation timestamp | `2025-05-10T14:00:00Z` |
| `SystemModstamp` | DateTime | Last modified timestamp | `2025-05-28T09:30:00Z` |

### Case

Customer support cases for tracking issues, returns, and inquiries.

**Key Relationships:**
- `Case.AccountId` -> `Account.Id`
- `Case.ContactId` -> `Contact.Id`

**Watermark Column:** `SystemModstamp`

**Bronze Layer Path:** `bronze/crm_salesforce/cases/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `Id` | ID(18) | Salesforce record ID (primary key) | `500Dn00000E5f6gXYZ` |
| `CaseNumber` | AutoNumber | Human-readable case number | `00045123` |
| `AccountId` | Reference(Account) | Associated account | `001Dn00000A1b2cXYZ` |
| `ContactId` | Reference(Contact) | Associated contact | `003Dn00000B2c3dXYZ` |
| `Subject` | String(255) | Case subject | `Bearing 6205 early failure` |
| `Description` | TextArea(32000) | Case description | `Customer reports premature...` |
| `Type` | Picklist | Case type | `Quality Issue` |
| `Priority` | Picklist | Priority level | `High` |
| `Status` | Picklist | Case status | `In Progress` |
| `Origin` | Picklist | Case origin channel | `Email` |
| `CreatedDate` | DateTime | Record creation timestamp | `2025-05-20T10:00:00Z` |
| `ClosedDate` | DateTime | Case closed timestamp | `null` |
| `SystemModstamp` | DateTime | Last modified timestamp | `2025-06-01T15:45:00Z` |

### Product2

Salesforce product catalog, mirroring materials from SAP MARA.

**Key Relationships:**
- `Product2.ProductCode` -> `MARA.MATNR` (cross-system link)
- `Product2.Id` <- `PricebookEntry.Product2Id` (one-to-many)

**Watermark Column:** `SystemModstamp`

**Bronze Layer Path:** `bronze/crm_salesforce/products/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `Id` | ID(18) | Salesforce record ID (primary key) | `01tDn00000F6g7hXYZ` |
| `Name` | String(255) | Product name | `Carbon Steel Coil HR 2.0mm` |
| `ProductCode` | String(255) | Product code (= SAP MATNR) | `0000000001` |
| `Family` | Picklist | Product family | `Steel & Metal Products` |
| `Description` | TextArea(4000) | Product description | `Hot-rolled carbon steel...` |
| `IsActive` | Boolean | Whether product is active | `true` |
| `CreatedDate` | DateTime | Record creation timestamp | `2023-01-15T12:00:00Z` |
| `SystemModstamp` | DateTime | Last modified timestamp | `2025-04-20T10:00:00Z` |

### PricebookEntry

Price records linking products to pricebooks with list prices.

**Key Relationships:**
- `PricebookEntry.Product2Id` -> `Product2.Id`
- `PricebookEntry.Pricebook2Id` -> `Pricebook2.Id`

**Watermark Column:** `SystemModstamp`

**Bronze Layer Path:** `bronze/crm_salesforce/pricebook_entries/`

| Field Name | Type | Description | Sample Value |
|------------|------|-------------|--------------|
| `Id` | ID(18) | Salesforce record ID (primary key) | `01uDn00000G7h8iXYZ` |
| `Pricebook2Id` | Reference(Pricebook2) | Parent pricebook | `01sDn000001StdPB` |
| `Product2Id` | Reference(Product2) | Associated product | `01tDn00000F6g7hXYZ` |
| `UnitPrice` | Currency | List price | `0.85` |
| `CurrencyIsoCode` | String(3) | Currency code | `USD` |
| `IsActive` | Boolean | Whether entry is active | `true` |
| `UseStandardPrice` | Boolean | Uses standard pricebook price | `false` |
| `CreatedDate` | DateTime | Record creation timestamp | `2023-01-15T12:05:00Z` |
| `SystemModstamp` | DateTime | Last modified timestamp | `2025-03-10T08:30:00Z` |

---

## Cross-System Linkages

The following identifiers enable joining data across SAP and Salesforce in the Silver
and Gold layers of the Medallion architecture.

### Customer Linkage

```
SAP KNA1.KUNNR  <──────────>  Salesforce Account.sap_customer_number__c
   (e.g. "0000001234")              (e.g. "0000001234")
```

- **Direction:** Bidirectional -- SAP KUNNR is stored as a custom field on the
  Salesforce Account object.
- **Cardinality:** 1:1 (one SAP customer maps to exactly one Salesforce Account).
- **Resolution:** During Silver layer transformation, records are joined on this
  shared key to produce a unified customer dimension.
- **Governance:** The mapping is maintained by the master data team. New customers
  created in either system must have the cross-reference populated before the next
  ETL cycle.

### Product / Material Linkage

```
SAP MARA.MATNR  <──────────>  Salesforce Product2.ProductCode
   (e.g. "0000000001")              (e.g. "0000000001")
```

- **Direction:** Bidirectional -- SAP material numbers are used as Salesforce
  `ProductCode` values.
- **Cardinality:** 1:1 (one SAP material maps to one Salesforce Product2 record).
- **Note:** Not all SAP materials exist in Salesforce. Only materials with
  `MTART` in (`FERT`, `HALB`) -- finished and semi-finished goods -- are
  typically synced to the CRM product catalog.

### Order Linkage

```
SAP VBAK.VBELN  <──────────>  Salesforce Opportunity.sap_order_number__c
   (e.g. "0000012345")              (e.g. "0000012345")
```

- **Direction:** SAP to Salesforce -- once an Opportunity is "Closed Won" and
  a sales order is created in SAP, the SAP order number is written back to
  the Opportunity record.
- **Cardinality:** 1:1 (one Opportunity yields at most one SAP sales order).

---

## Data Lake Folder Structure

All source data lands in the Fabric Lakehouse under a structured folder hierarchy.
The Bronze layer preserves raw data exactly as received from source systems.

```
lakehouse/
|
+-- bronze/
|   |
|   +-- erp_sap/
|   |   +-- kna1/                    # Customer Master
|   |   |   +-- data.parquet
|   |   +-- mara/                    # Material Master
|   |   |   +-- data.parquet
|   |   +-- mard/                    # Plant Stock
|   |   |   +-- data.parquet
|   |   +-- vbak/                    # Sales Order Header
|   |   |   +-- data.parquet
|   |   +-- vbap/                    # Sales Order Item
|   |   |   +-- data.parquet
|   |   +-- vbrk/                    # Billing Header
|   |   |   +-- data.parquet
|   |   +-- vbrp/                    # Billing Item
|   |   |   +-- data.parquet
|   |   +-- likp/                    # Delivery Header
|   |   |   +-- data.parquet
|   |   +-- lips/                    # Delivery Item
|   |       +-- data.parquet
|   |
|   +-- crm_salesforce/
|   |   +-- accounts/                # Account records
|   |   |   +-- data.parquet
|   |   +-- contacts/                # Contact records
|   |   |   +-- data.parquet
|   |   +-- opportunities/           # Opportunity records
|   |   |   +-- data.parquet
|   |   +-- leads/                   # Lead records
|   |   |   +-- data.parquet
|   |   +-- cases/                   # Case records
|   |   |   +-- data.parquet
|   |   +-- products/                # Product2 records
|   |   |   +-- data.parquet
|   |   +-- pricebook_entries/       # PricebookEntry records
|   |       +-- data.parquet
|   |
|   +-- iot/
|       +-- iot_telemetry/           # IoT sensor telemetry
|           +-- data.parquet
|
+-- silver/
|   +-- dim_customer/                # Unified customer dimension (SAP + SF)
|   +-- dim_material/                # Unified material/product dimension
|   +-- fact_sales_order/            # Sales order fact (header + items)
|   +-- fact_billing/                # Billing fact (header + items)
|   +-- fact_delivery/               # Delivery fact (header + items)
|   +-- fact_iot_telemetry/          # Cleansed IoT telemetry
|   +-- dim_plant/                   # Plant dimension
|   +-- dim_date/                    # Date dimension
|
+-- gold/
    +-- sales_performance/           # Aggregated sales KPIs
    +-- customer_360/                # Customer 360 view
    +-- inventory_snapshot/          # Point-in-time inventory
    +-- iot_equipment_health/        # Equipment health scores
    +-- product_profitability/       # Product margin analysis
```

### Bronze Metadata Columns

Every Bronze table includes the following system-generated metadata columns:

| Column | Type | Description |
|--------|------|-------------|
| `_bronze_ingestion_timestamp` | String (ISO 8601) | UTC timestamp when the row was ingested |
| `_bronze_batch_id` | String (UUID) | Unique identifier for the ingestion batch |
| `_bronze_pipeline_run_id` | String | Pipeline run identifier for traceability |
| `_bronze_source_system` | String | Source system name (`erp_sap`, `crm_salesforce`, `iot`) |
| `_bronze_source_table` | String | Source table/entity name (e.g., `vbak`, `accounts`) |
| `_bronze_load_type` | String | Load type: `full` or `incremental` |
| `_bronze_file_path` | String | Path to the source file in the lakehouse |
| `_bronze_row_hash` | String (SHA-256) | Hash of all source columns for change detection |

---

## RAG Document Structure

The RAG (Retrieval-Augmented Generation) pipeline produces three types of documents
stored in the `rag-documents` ADLS container. These documents are indexed into
PostgreSQL + pgvector by the `ai/rag/indexing/index_product_catalog.py` pipeline.

| Document Type | Count | Format | Generator |
|--------------|-------|--------|-----------|
| Product Catalogs | ~2,000 | JSON + CSV | `rag_document_generator.py` |
| Customer 360 Profiles | ~10,000 | Markdown | `chunk_for_rag.py` |
| Transaction Lifecycle | ~70,000 | JSON | `chunk_for_rag.py` |
| Equipment Health Reports | ~200 | Markdown | `chunk_for_rag.py` |
| **Total** | **~82,000** | | |

```
rag-documents/
|
+-- product-catalog/
|   |
|   +-- material_0000000001.json     # Per-material JSON files
|   +-- material_0000000002.json     #   (material_number, product_name,
|   +-- ...                          #    category, description,
|   +-- material_0000002000.json     #    specifications, applications,
|   |                                #    compliance)
|   +-- catalog_master.csv           # Bulk CSV with all materials
|
+-- customer-360/
|   |
|   +-- customer_0000000001.md       # Per-customer Markdown (all 10K)
|   +-- customer_0000000002.md       #   Aggregates SAP + Salesforce data:
|   +-- ...                          #   orders, pipeline, cases, contacts
|   +-- customer_0000010000.md
|
+-- transactions/
|   |
|   +-- order_0000000001.json        # Per-order lifecycle JSON
|   +-- order_0000000002.json        #   Significant orders only:
|   +-- ...                          #   > $50K OR last 6 months
|   +-- order_XXXXXXXXXX.json        #   header, items, billing, delivery
|
+-- equipment-health/
    |
    +-- equipment_EQ-1100-A-006.md   # Per-equipment health report
    +-- equipment_EQ-1100-A-016.md   #   ML-predicted health scores,
    +-- ...                          #   sensor readings, trends,
    +-- equipment_EQ-3100-D-029.md   #   anomalies, maintenance history
```

### Product Catalog JSON Schema

Each product catalog JSON file follows this structure, compatible with the
`ProductCatalogParser._parse_json_catalog()` method in the indexing pipeline:

```json
{
  "material_number": "0000000001",
  "product_name": "Carbon Steel Coil HR 2.0mm",
  "category": "Steel & Metal Products",
  "description": "Detailed technical description...",
  "specifications": {
    "weight_kg": 125.5,
    "unit_of_measure": "KG",
    "base_price_usd": 0.85,
    "material_grade": "A36",
    "surface_finish": "Hot-rolled",
    "operating_temp_range": "-40 to 400 °C"
  },
  "applications": [
    "Structural fabrication",
    "Automotive body panels",
    "Pressure vessel manufacturing"
  ],
  "compliance": [
    "ISO 9001:2015",
    "EN 10204 Type 3.1",
    "RoHS Directive 2011/65/EU"
  ]
}
```

### Customer 360 Markdown Structure

Each Customer 360 profile is a rich Markdown document aggregating data from both
SAP ERP and Salesforce CRM. Generated by `chunk_for_rag.py` for all 10,000
customers. Includes:

- `# Customer 360: {Company Name}` heading
- **Overview** table with SAP KUNNR, Salesforce Account ID, industry, location, revenue
- **Order Summary** with total orders, revenue, average order value, top products, YoY trend
- **Recent Orders** table (last 6 months) with order number, date, items, value, status
- **Salesforce Pipeline** with open/won/lost opportunities and win rate
- **Support History** with case counts, open issues, avg resolution time, top issue types
- **Key Contacts** table with name, title, email

### Transaction Lifecycle JSON Schema

Each transaction document captures the full lifecycle of a significant sales order
(orders > $50,000 OR created in the last 6 months). Generated by `chunk_for_rag.py`.

```json
{
  "document_type": "sales_order_lifecycle",
  "order_number": "0000145023",
  "customer": {
    "kunnr": "0000005432",
    "name": "Acme Manufacturing Corp",
    "city": "Detroit",
    "country": "US"
  },
  "order_header": {
    "created_date": "2025-09-15",
    "order_type": "ZOR",
    "sales_org": "1000",
    "net_value": 78500.00,
    "currency": "USD",
    "customer_po": "PO-AC-2025-0892"
  },
  "line_items": [
    {
      "item": "000010",
      "material": "0000000001",
      "material_name": "Carbon Steel Coil HR 2.0mm",
      "quantity": 500,
      "unit": "KG",
      "net_value": 42500.00,
      "plant": "1100"
    }
  ],
  "billing": {
    "billing_doc": "0090123456",
    "billing_date": "2025-09-20",
    "net_value": 78500.00
  },
  "delivery": {
    "delivery_doc": "0080198765",
    "planned_gi_date": "2025-09-18",
    "actual_gi_date": "2025-09-18",
    "shipping_point": "SH01"
  },
  "status": "Delivered and Billed",
  "salesforce_opportunity": {
    "id": "006Dn00000X1y2zABC",
    "stage": "Closed Won",
    "amount": 78500.00
  }
}
```

### Equipment Health Markdown Structure

Each Equipment Health Report is a Markdown document generated from ML predictions
(Random Forest classifier) and IoT telemetry data. Generated by
`chunk_for_rag.py` (`EquipmentHealthGenerator`) for all ~200 equipment units.

- `# Equipment Health Report: {Equipment ID}` heading
- **Overview** table with equipment ID, plant, production line, health score (0-100),
  failure risk (Low/Medium/High/Critical), estimated RUL (days), last maintenance date
- **Current Sensor Readings** table with latest values, normal ranges, and status
  (Normal/Elevated/Critical) for temperature, pressure, vibration, humidity, flow_rate, power
- **Trend Analysis** (last 90 days) with percentage changes per sensor type
- **Anomaly History** table with recent non-GOOD quality flag readings
- **Maintenance History** table with lifecycle events (state transitions)
- **Recommended Actions** based on failure risk level
- **Top Risk Factors** from ML feature importances

### IoT Telemetry

Manufacturing equipment sensor data with realistic degradation patterns.

**Equipment Lifecycle State Machine:**
```
HEALTHY → DEGRADING → WARNING → CRITICAL → FAILED → MAINTAINED → HEALTHY (repeat)
```

| Parameter | Value |
|-----------|-------|
| Equipment count | ~200 (across 5 plants, 4 production lines) |
| Sensor types | temperature, pressure, vibration, humidity, flow_rate, power |
| Total readings | 500,000 |
| Time range | 2024-01-01 to 2025-12-31 |
| Reading interval | 30-120 minutes per device |

**Bronze Layer Paths:**
- `bronze/iot/telemetry/iot_telemetry.parquet` — sensor readings with equipment state
- `bronze/iot/telemetry/equipment_lifecycle_events.parquet` — ground truth state transitions

### Predictive Maintenance ML Pipeline

A scikit-learn Random Forest classifier trained on IoT telemetry features.

| Output | Path | Description |
|--------|------|-------------|
| Model | `ml-models/predictive_maintenance_rf.joblib` | Trained RandomForest (100 trees, max depth 12) |
| Scaler | `ml-models/predictive_maintenance_scaler.joblib` | StandardScaler for feature normalization |
| Report | `ml-models/training_report.json` | Accuracy, F1, confusion matrix, feature importances |
| Features | `ml-features/equipment_features.parquet` | Weekly features per equipment (39 features) |
| Predictions | `gold/equipment_health_scores.parquet` | Per-equipment health scores and risk levels |

**Top Features:** `bad_reading_pct` (16%), `anomaly_count` (13%), `temperature_mean` (5.3%)

**Health Score Distribution:** ~87% Low, ~8% Medium, ~3% Critical, ~2% High
