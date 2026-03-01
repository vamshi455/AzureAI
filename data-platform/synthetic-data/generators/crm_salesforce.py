"""Salesforce CRM synthetic data generator for Manufacturing + Sales data platform.

Generates realistic data for 7 Salesforce entities:
  - Accounts, Contacts, Opportunities, Leads, Cases, Products, PricebookEntries

All output DataFrames use string columns to match the bronze layer schema.
"""

import uuid
from datetime import date, datetime, timedelta

import pandas as pd
from tqdm import tqdm

from generators.base import SharedMasterData, bronze_metadata, row_hash, fake
from config import (
    VOLUMES,
    SF_INDUSTRIES,
    SF_LEAD_SOURCES,
    SF_OPPORTUNITY_STAGES,
    SF_CASE_PRIORITIES,
    SF_CASE_TYPES,
    DATE_RANGE_START,
    DATE_RANGE_END,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SOURCE_SYSTEM = "salesforce"

# Opportunity stage -> probability mapping (correlates stage with likelihood)
_STAGE_PROBABILITY = {
    "Prospecting": 10,
    "Qualification": 20,
    "Needs Analysis": 40,
    "Value Proposition": 60,
    "Negotiation": 80,
    "Closed Won": 100,
    "Closed Lost": 0,
}

# Forecast category derived from stage
_STAGE_FORECAST = {
    "Prospecting": "Pipeline",
    "Qualification": "Pipeline",
    "Needs Analysis": "Best Case",
    "Value Proposition": "Best Case",
    "Negotiation": "Commit",
    "Closed Won": "Closed",
    "Closed Lost": "Omitted",
}

# Realistic manufacturing job titles for contacts
_MFG_TITLES = [
    "VP of Procurement",
    "Chief Operations Officer",
    "Plant Manager",
    "Purchasing Manager",
    "Supply Chain Director",
    "Engineering Manager",
    "Quality Assurance Director",
    "Maintenance Supervisor",
    "Production Manager",
    "Director of Manufacturing",
    "Buyer",
    "Senior Buyer",
    "Commodity Manager",
    "Materials Manager",
    "Inventory Control Manager",
    "Logistics Coordinator",
    "Technical Director",
    "Process Engineer",
    "Facilities Manager",
    "Operations Analyst",
]

# Departments found at manufacturing companies
_MFG_DEPARTMENTS = [
    "Procurement",
    "Operations",
    "Engineering",
    "Quality",
    "Maintenance",
    "Supply Chain",
    "Production",
    "Logistics",
    "Finance",
    "Executive",
]

# Descriptive opportunity name fragments for manufacturing B2B deals
_OPP_PRODUCT_PHRASES = [
    "Carbon Steel Supply Agreement",
    "Precision Bearing Annual Contract",
    "Hydraulic System Upgrade",
    "Electric Motor Fleet Replacement",
    "Pneumatic Component Retrofit",
    "Fastener Blanket Purchase Order",
    "Seal & Gasket Maintenance Kit",
    "Pump Station Expansion",
    "Sensor Instrumentation Rollout",
    "Industrial Lubricant Supply Deal",
    "Stainless Steel Plate Order",
    "Valve Replacement Program",
    "Automation Component Package",
    "Spare Parts Framework Agreement",
    "MRO Supplies Annual Contract",
    "Production Line Equipment Upgrade",
    "Conveyor System Components",
    "CNC Tooling Supply Agreement",
    "Filtration System Overhaul",
    "Heat Exchanger Replacement Parts",
]

# Pricebook identifiers and their price multipliers relative to standard
_PRICEBOOKS = [
    {"id": "01s000000000001AAA", "name": "Standard", "multiplier": 1.00},
    {"id": "01s000000000002AAA", "name": "Industrial", "multiplier": 0.92},
    {"id": "01s000000000003AAA", "name": "Government", "multiplier": 0.85},
]

# Owner IDs (simulated Salesforce user ids for sales reps)
_OWNER_IDS = [f"005{fake.hexify(text='^^^^^^^^^^^^^^', upper=True)}" for _ in range(20)]

# Case subjects that sound like real manufacturing support tickets
_CASE_SUBJECTS = [
    "Motor overheating during continuous operation",
    "Bearing failure on production line B",
    "Incorrect part number shipped",
    "Request for material test certificates",
    "Delivery delay - PO #{po}",
    "Quality deviation report - batch #{batch}",
    "Hydraulic leak on press unit #{unit}",
    "Pricing discrepancy on invoice #{inv}",
    "RMA request for defective seals",
    "Installation guide needed for new pump",
    "Vibration readings above threshold on compressor",
    "Request for updated SDS documentation",
    "Short shipment on order #{po}",
    "Corrosion issue on supplied steel coils",
    "Calibration certificate request for sensors",
    "Warranty claim - premature valve failure",
    "Lead time inquiry for custom extrusions",
    "Product substitution approval needed",
    "Packaging damage during transit",
    "Technical specifications mismatch",
]


def _sf_uuid() -> str:
    """Return a Salesforce-style 18-char alphanumeric id."""
    return str(uuid.uuid4()).replace("-", "")[:18]


def _random_iso_datetime(start: str = DATE_RANGE_START, end: str = DATE_RANGE_END) -> str:
    """Return an ISO 8601 datetime string within the configured date range."""
    start_dt = datetime.strptime(start, "%Y-%m-%d") if isinstance(start, str) else start
    end_dt = datetime.strptime(end, "%Y-%m-%d") if isinstance(end, str) else end
    d = fake.date_time_between(start_date=start_dt, end_date=end_dt)
    return d.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _random_iso_date(start: str = DATE_RANGE_START, end: str = DATE_RANGE_END) -> str:
    """Return an ISO 8601 date-only string within the configured date range."""
    start_d = date.fromisoformat(start) if isinstance(start, str) else start
    end_d = date.fromisoformat(end) if isinstance(end, str) else end
    d = fake.date_between(start_date=start_d, end_date=end_d)
    return d.strftime("%Y-%m-%d")


def _last_modified_after(created_iso: str) -> str:
    """Return an ISO 8601 datetime guaranteed to be >= the created datetime."""
    try:
        created = datetime.strptime(created_iso[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        created = datetime.strptime(created_iso[:10], "%Y-%m-%d")
    end_dt = datetime.strptime(DATE_RANGE_END, "%Y-%m-%d")
    if created >= end_dt:
        return created.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    modified = fake.date_time_between(start_date=created, end_date=end_dt)
    return modified.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _stringify_df(df: pd.DataFrame) -> pd.DataFrame:
    """Convert every column to string so the DataFrame matches bronze schema."""
    return df.astype(str)


# ============================================================================
# Generator class
# ============================================================================


class SalesforceGenerator:
    """Generates synthetic Salesforce CRM data for a Manufacturing data platform."""

    def __init__(self, master: SharedMasterData):
        self.master = master

    # ------------------------------------------------------------------
    # 1. Accounts
    # ------------------------------------------------------------------
    def generate_accounts(self) -> pd.DataFrame:
        """Generate Account records from shared customer master data."""
        rows: list[dict] = []
        meta = bronze_metadata(_SOURCE_SYSTEM, "Account")

        for cust in self.master.customers:
            created = datetime.combine(
                cust["created_date"], datetime.min.time()
            ).strftime("%Y-%m-%dT%H:%M:%S.000+0000") if not isinstance(
                cust["created_date"], str
            ) else cust["created_date"] + "T00:00:00.000+0000"

            row = {
                "Id": cust["sf_account_id"],
                "AccountNumber": cust["kunnr"],
                "Name": cust["name"],
                "Industry": cust["industry"],
                "Type": fake.random_element(
                    elements=["Customer"] * 7 + ["Prospect"] * 2 + ["Partner"]
                ),
                "Phone": cust["phone"],
                "Website": f"www.{cust['name'].lower().replace(' ', '').replace(',', '').replace('.', '')[:20]}.com",
                "BillingStreet": cust["street"],
                "BillingCity": cust["city"],
                "BillingState": cust["state"],
                "BillingPostalCode": cust["postal_code"],
                "BillingCountry": cust["country"],
                "AnnualRevenue": str(cust["revenue"]),
                "NumberOfEmployees": str(cust["employees"]),
                "OwnerId": fake.random_element(_OWNER_IDS),
                "Description": f"Manufacturing customer - {cust['industry']} sector",
                "CreatedDate": created,
                "LastModifiedDate": _last_modified_after(created),
                "IsDeleted": str(fake.boolean(chance_of_getting_true=2)).lower(),
                "SAPCustomerNumber": cust["kunnr"],
            }
            row.update(meta)
            row["_bronze_row_hash"] = row_hash(row)
            rows.append(row)

        return _stringify_df(pd.DataFrame(rows))

    # ------------------------------------------------------------------
    # 2. Contacts
    # ------------------------------------------------------------------
    def generate_contacts(self, accounts_df: pd.DataFrame) -> pd.DataFrame:
        """Generate Contact records spread across existing accounts."""
        num = VOLUMES["contacts"]
        account_ids = accounts_df["Id"].tolist()
        rows: list[dict] = []
        meta = bronze_metadata(_SOURCE_SYSTEM, "Contact")

        for _ in tqdm(range(num), desc="Contacts"):
            acct_id = fake.random_element(account_ids)
            created = _random_iso_datetime()
            first = fake.first_name()
            last = fake.last_name()

            row = {
                "Id": _sf_uuid(),
                "AccountId": acct_id,
                "FirstName": first,
                "LastName": last,
                "Email": f"{first.lower()}.{last.lower()}@{fake.free_email_domain()}",
                "Phone": fake.phone_number(),
                "Title": fake.random_element(_MFG_TITLES),
                "Department": fake.random_element(_MFG_DEPARTMENTS),
                "MailingStreet": fake.street_address(),
                "MailingCity": fake.city(),
                "MailingState": fake.state_abbr(),
                "MailingPostalCode": fake.zipcode(),
                "MailingCountry": fake.random_element(
                    ["US", "US", "US", "CA", "GB", "DE", "JP"]
                ),
                "CreatedDate": created,
                "LastModifiedDate": _last_modified_after(created),
                "IsDeleted": str(fake.boolean(chance_of_getting_true=2)).lower(),
            }
            row.update(meta)
            row["_bronze_row_hash"] = row_hash(row)
            rows.append(row)

        return _stringify_df(pd.DataFrame(rows))

    # ------------------------------------------------------------------
    # 3. Opportunities
    # ------------------------------------------------------------------
    def generate_opportunities(self, accounts_df: pd.DataFrame) -> pd.DataFrame:
        """Generate Opportunity records tied to accounts with realistic amounts."""
        num = VOLUMES["opportunities"]
        account_ids = accounts_df["Id"].tolist()
        rows: list[dict] = []
        meta = bronze_metadata(_SOURCE_SYSTEM, "Opportunity")

        for _ in tqdm(range(num), desc="Opportunities"):
            stage = fake.random_element(SF_OPPORTUNITY_STAGES)
            is_closed = stage in ("Closed Won", "Closed Lost")
            is_won = stage == "Closed Won"
            probability = _STAGE_PROBABILITY[stage]
            # Add small jitter to non-terminal probabilities
            if not is_closed:
                probability = max(0, min(100, probability + fake.random_int(-5, 5)))

            created = _random_iso_datetime()
            close_date = _random_iso_date(
                start=created[:10],
                end=DATE_RANGE_END,
            )

            # Realistic B2B manufacturing deal amounts: $5K - $2M
            amount = round(fake.pyfloat(min_value=5_000, max_value=2_000_000), 2)

            acct_id = fake.random_element(account_ids)
            opp_name = fake.random_element(_OPP_PRODUCT_PHRASES)

            row = {
                "Id": _sf_uuid(),
                "AccountId": acct_id,
                "Name": opp_name,
                "StageName": stage,
                "Amount": str(amount),
                "Probability": str(probability),
                "CloseDate": close_date,
                "Type": fake.random_element(
                    elements=["New Business"] * 4 + ["Existing Business"] * 6
                ),
                "LeadSource": fake.random_element(SF_LEAD_SOURCES),
                "ForecastCategory": _STAGE_FORECAST[stage],
                "IsClosed": str(is_closed).lower(),
                "IsWon": str(is_won).lower(),
                "CreatedDate": created,
                "LastModifiedDate": _last_modified_after(created),
            }
            row.update(meta)
            row["_bronze_row_hash"] = row_hash(row)
            rows.append(row)

        return _stringify_df(pd.DataFrame(rows))

    # ------------------------------------------------------------------
    # 4. Leads
    # ------------------------------------------------------------------
    def generate_leads(self) -> pd.DataFrame:
        """Generate Lead records with 20 percent converted to existing accounts."""
        num = VOLUMES["leads"]
        account_ids = [c["sf_account_id"] for c in self.master.customers]
        rows: list[dict] = []
        meta = bronze_metadata(_SOURCE_SYSTEM, "Lead")

        statuses = ["New"] * 4 + ["Working"] * 3 + ["Qualified"] * 2 + ["Unqualified"]
        ratings = ["Hot"] * 2 + ["Warm"] * 5 + ["Cold"] * 3

        for _ in tqdm(range(num), desc="Leads"):
            created = _random_iso_datetime()
            is_converted = fake.boolean(chance_of_getting_true=20)

            converted_acct = ""
            converted_date = ""
            if is_converted:
                converted_acct = fake.random_element(account_ids)
                converted_date = _random_iso_date(start=created[:10], end=DATE_RANGE_END)

            first = fake.first_name()
            last = fake.last_name()
            company = fake.company()

            row = {
                "Id": _sf_uuid(),
                "FirstName": first,
                "LastName": last,
                "Company": company,
                "Email": f"{first.lower()}.{last.lower()}@{fake.domain_name()}",
                "Phone": fake.phone_number(),
                "Title": fake.random_element(_MFG_TITLES),
                "Industry": fake.random_element(SF_INDUSTRIES),
                "LeadSource": fake.random_element(SF_LEAD_SOURCES),
                "Status": fake.random_element(statuses),
                "Rating": fake.random_element(ratings),
                "AnnualRevenue": str(
                    round(fake.pyfloat(min_value=500_000, max_value=100_000_000), 2)
                ),
                "NumberOfEmployees": str(fake.random_int(min=10, max=5000)),
                "Description": f"Potential {fake.random_element(SF_INDUSTRIES).lower()} customer - {fake.bs()}",
                "ConvertedAccountId": converted_acct,
                "ConvertedDate": converted_date,
                "CreatedDate": created,
                "LastModifiedDate": _last_modified_after(created),
                "IsDeleted": str(fake.boolean(chance_of_getting_true=2)).lower(),
            }
            row.update(meta)
            row["_bronze_row_hash"] = row_hash(row)
            rows.append(row)

        return _stringify_df(pd.DataFrame(rows))

    # ------------------------------------------------------------------
    # 5. Cases
    # ------------------------------------------------------------------
    def generate_cases(
        self, accounts_df: pd.DataFrame, contacts_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Generate support Case records linked to accounts and contacts."""
        num = VOLUMES["cases"]
        account_ids = accounts_df["Id"].tolist()
        contact_ids = contacts_df["Id"].tolist()
        rows: list[dict] = []
        meta = bronze_metadata(_SOURCE_SYSTEM, "Case")

        for _ in tqdm(range(num), desc="Cases"):
            created = _random_iso_datetime()
            status = fake.random_element(
                elements=["New"] * 3 + ["In Progress"] * 4 + ["Escalated"] * 1 + ["Closed"] * 4
            )
            is_closed = status == "Closed"

            closed_date = ""
            if is_closed:
                closed_date = _last_modified_after(created)

            # Build a realistic subject line
            subject_template = fake.random_element(_CASE_SUBJECTS)
            subject = subject_template.format(
                po=fake.random_int(min=4500000, max=4599999),
                batch=fake.bothify(text="B-####-??", letters="ABCDEF"),
                unit=fake.random_int(min=1, max=20),
                inv=fake.random_int(min=9000000, max=9099999),
            )

            row = {
                "Id": _sf_uuid(),
                "AccountId": fake.random_element(account_ids),
                "ContactId": fake.random_element(contact_ids),
                "Subject": subject,
                "Description": f"{subject}. {fake.sentence(nb_words=12)}",
                "Type": fake.random_element(SF_CASE_TYPES),
                "Priority": fake.random_element(SF_CASE_PRIORITIES),
                "Status": status,
                "Origin": fake.random_element(["Phone", "Email", "Web", "Chat"]),
                "CreatedDate": created,
                "ClosedDate": closed_date,
                "LastModifiedDate": closed_date if is_closed else _last_modified_after(created),
                "IsDeleted": str(fake.boolean(chance_of_getting_true=1)).lower(),
            }
            row.update(meta)
            row["_bronze_row_hash"] = row_hash(row)
            rows.append(row)

        return _stringify_df(pd.DataFrame(rows))

    # ------------------------------------------------------------------
    # 6. Products
    # ------------------------------------------------------------------
    def generate_products(self) -> pd.DataFrame:
        """Generate Product2 records from shared material master data."""
        rows: list[dict] = []
        meta = bronze_metadata(_SOURCE_SYSTEM, "Product2")

        for mat in self.master.materials:
            created = _random_iso_datetime(
                start=DATE_RANGE_START,
                end=DATE_RANGE_START,  # products created at range start
            )

            row = {
                "Id": _sf_uuid(),
                "Name": mat["name"],
                "ProductCode": mat["matnr"],
                "Family": mat["group_name"],
                "Description": f"{mat['name']} - {mat['group_name']} ({mat['type']}, {mat['uom']})",
                "IsActive": str(fake.boolean(chance_of_getting_true=95)).lower(),
                "UnitPrice": str(mat["base_price"]),
                "CreatedDate": created,
                "LastModifiedDate": _last_modified_after(created),
            }
            row.update(meta)
            row["_bronze_row_hash"] = row_hash(row)
            rows.append(row)

        return _stringify_df(pd.DataFrame(rows))

    # ------------------------------------------------------------------
    # 7. Pricebook Entries
    # ------------------------------------------------------------------
    def generate_pricebook_entries(self, products_df: pd.DataFrame) -> pd.DataFrame:
        """Generate PricebookEntry records across multiple pricebooks."""
        num = VOLUMES["pricebook_entries"]
        product_rows = products_df.to_dict("records")
        rows: list[dict] = []
        meta = bronze_metadata(_SOURCE_SYSTEM, "PricebookEntry")

        for _ in range(num):
            product = fake.random_element(product_rows)
            pricebook = fake.random_element(_PRICEBOOKS)

            base_price = float(product["UnitPrice"])
            # Apply pricebook multiplier with additional +-15% jitter
            jitter = 1.0 + (fake.pyfloat(min_value=-15, max_value=15) / 100.0)
            unit_price = round(base_price * pricebook["multiplier"] * jitter, 2)
            unit_price = max(0.01, unit_price)  # never negative

            is_standard = pricebook["name"] == "Standard"
            created = _random_iso_datetime()

            row = {
                "Id": _sf_uuid(),
                "Pricebook2Id": pricebook["id"],
                "Product2Id": product["Id"],
                "UnitPrice": str(unit_price),
                "IsActive": str(fake.boolean(chance_of_getting_true=92)).lower(),
                "UseStandardPrice": str(is_standard).lower(),
                "CreatedDate": created,
                "LastModifiedDate": _last_modified_after(created),
            }
            row.update(meta)
            row["_bronze_row_hash"] = row_hash(row)
            rows.append(row)

        return _stringify_df(pd.DataFrame(rows))

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------
    def generate_all(self) -> dict[str, pd.DataFrame]:
        """Generate all Salesforce entities in dependency order.

        Returns a dict mapping entity name to its DataFrame.
        """
        accounts_df = self.generate_accounts()
        contacts_df = self.generate_contacts(accounts_df)
        opportunities_df = self.generate_opportunities(accounts_df)
        leads_df = self.generate_leads()
        cases_df = self.generate_cases(accounts_df, contacts_df)
        products_df = self.generate_products()
        pricebook_entries_df = self.generate_pricebook_entries(products_df)

        return {
            "accounts": accounts_df,
            "contacts": contacts_df,
            "opportunities": opportunities_df,
            "leads": leads_df,
            "cases": cases_df,
            "products": products_df,
            "pricebook_entries": pricebook_entries_df,
        }
