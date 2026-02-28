#!/usr/bin/env python3
"""
Main orchestrator for synthetic data generation.

Generates realistic Manufacturing + Sales data for:
  - ERP (SAP SD): 9 tables (VBAK, VBAP, KNA1, MARA, MARD, VBRK, VBRP, LIKP, LIPS)
  - CRM (Salesforce): 7 entities (Accounts, Contacts, Opportunities, Leads, Cases, Products, PricebookEntries)
  - IoT: Manufacturing equipment telemetry
  - RAG Documents: Product catalogs and customer profiles for AI Foundry

Usage:
    python generate_all.py                    # Generate all data locally
    python generate_all.py --upload           # Generate and upload to ADLS Gen2
    python generate_all.py --upload-only      # Upload existing local data (skip generation)
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from config import OUTPUT_BRONZE, OUTPUT_RAG, OUTPUT_DIR, VOLUMES


def ensure_output_dirs():
    """Create local output directory structure."""
    dirs = [
        OUTPUT_BRONZE / "erp_sap" / "kna1",
        OUTPUT_BRONZE / "erp_sap" / "mara",
        OUTPUT_BRONZE / "erp_sap" / "mard",
        OUTPUT_BRONZE / "erp_sap" / "vbak",
        OUTPUT_BRONZE / "erp_sap" / "vbap",
        OUTPUT_BRONZE / "erp_sap" / "vbrk",
        OUTPUT_BRONZE / "erp_sap" / "vbrp",
        OUTPUT_BRONZE / "erp_sap" / "likp",
        OUTPUT_BRONZE / "erp_sap" / "lips",
        OUTPUT_BRONZE / "crm_salesforce" / "accounts",
        OUTPUT_BRONZE / "crm_salesforce" / "contacts",
        OUTPUT_BRONZE / "crm_salesforce" / "opportunities",
        OUTPUT_BRONZE / "crm_salesforce" / "leads",
        OUTPUT_BRONZE / "crm_salesforce" / "cases",
        OUTPUT_BRONZE / "crm_salesforce" / "products",
        OUTPUT_BRONZE / "crm_salesforce" / "pricebook_entries",
        OUTPUT_BRONZE / "iot" / "telemetry",
        OUTPUT_RAG / "product-catalog",
        OUTPUT_RAG / "customer-profiles",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def save_parquet(df: pd.DataFrame, path: Path, name: str):
    """Save DataFrame as Parquet file."""
    filepath = path / f"{name}.parquet"
    df.to_parquet(filepath, engine="pyarrow", index=False)
    size_mb = filepath.stat().st_size / (1024 * 1024)
    print(f"  Saved {filepath.name}: {len(df):,} rows, {size_mb:.2f} MB")
    return filepath


def generate_data():
    """Generate all synthetic data and save locally as Parquet."""
    from generators.base import SharedMasterData
    from generators.erp_sap import SAPSDGenerator
    from generators.crm_salesforce import SalesforceGenerator
    from generators.iot_telemetry import IoTTelemetryGenerator
    from rag_document_generator import RAGDocumentGenerator

    start = time.time()
    ensure_output_dirs()

    # Step 1: Generate shared master data
    print("=" * 60)
    print("Step 1/5: Generating shared master data...")
    print("=" * 60)
    master = SharedMasterData().generate()
    print(f"  Materials: {len(master.materials):,}")
    print(f"  Customers: {len(master.customers):,}")

    # Step 2: Generate SAP SD data
    print("\n" + "=" * 60)
    print("Step 2/5: Generating ERP (SAP SD) data...")
    print("=" * 60)
    sap = SAPSDGenerator(master)
    sap_data = sap.generate_all()
    for table_name, df in sap_data.items():
        save_parquet(df, OUTPUT_BRONZE / "erp_sap" / table_name, table_name)

    # Step 3: Generate Salesforce CRM data
    print("\n" + "=" * 60)
    print("Step 3/5: Generating CRM (Salesforce) data...")
    print("=" * 60)
    sf = SalesforceGenerator(master)
    sf_data = sf.generate_all()
    for entity_name, df in sf_data.items():
        save_parquet(df, OUTPUT_BRONZE / "crm_salesforce" / entity_name, entity_name)

    # Step 4: Generate IoT telemetry
    print("\n" + "=" * 60)
    print("Step 4/5: Generating IoT telemetry data...")
    print("=" * 60)
    iot = IoTTelemetryGenerator(master)
    iot_data = iot.generate_all()
    for name, df in iot_data.items():
        save_parquet(df, OUTPUT_BRONZE / "iot" / "telemetry", name)

    # Step 5: Generate RAG documents
    print("\n" + "=" * 60)
    print("Step 5/5: Generating RAG documents...")
    print("=" * 60)
    rag = RAGDocumentGenerator(master, OUTPUT_RAG)
    rag_count = rag.generate_all()
    print(f"  Generated {rag_count} RAG documents")

    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"Data generation complete in {elapsed:.1f}s")
    print("=" * 60)

    # Summary
    total_rows = sum(len(df) for df in sap_data.values()) + \
                 sum(len(df) for df in sf_data.values()) + \
                 sum(len(df) for df in iot_data.values())
    print(f"\nTotal rows generated: {total_rows:,}")
    print(f"Output directory: {OUTPUT_DIR}")

    return True


def upload_data():
    """Upload generated data to ADLS Gen2 lakehouse."""
    from upload_to_lakehouse import LakehouseUploader

    uploader = LakehouseUploader()
    uploader.upload_all()


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic Manufacturing + Sales data"
    )
    parser.add_argument(
        "--upload", action="store_true",
        help="Upload data to ADLS Gen2 after generation"
    )
    parser.add_argument(
        "--upload-only", action="store_true",
        help="Skip generation, only upload existing local data"
    )
    args = parser.parse_args()

    if args.upload_only:
        upload_data()
        return

    success = generate_data()
    if not success:
        sys.exit(1)

    if args.upload:
        upload_data()


if __name__ == "__main__":
    main()
