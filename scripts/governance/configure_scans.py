#!/usr/bin/env python3
"""Configure scans for registered data sources in Microsoft Purview.

Creates scan rule sets, scans with MSI authentication, weekly schedules,
and triggers an initial full scan.

Usage:
    python configure_scans.py
    python configure_scans.py --run-now        # also run initial scan
    python configure_scans.py --no-schedule    # skip schedule setup
"""

import argparse
import uuid

from purview_client import get_scanning_client
from config import (
    ENVIRONMENT,
    ROOT_COLLECTION,
    SCAN_SCHEDULE_INTERVAL,
    SCAN_SCHEDULE_DAY,
    SCAN_SCHEDULE_HOUR,
)


def create_scan_ruleset(client) -> dict:
    """Create a custom scan rule set for the ADLS Gen2 lakehouse."""
    ruleset_name = f"ruleset-lakehouse-{ENVIRONMENT}"

    body = {
        "kind": "AdlsGen2",
        "properties": {
            "description": "Scan rule set for Manufacturing & Sales lakehouse data",
            "type": "Custom",
            "scanningRule": {
                "fileExtensions": [
                    "Parquet",
                    "JSON",
                    "CSV",
                ],
                "customFileExtensions": [],
            },
        },
    }

    print(f"Creating scan rule set: {ruleset_name}")
    result = client.scan_rulesets.create_or_update(
        scan_ruleset_name=ruleset_name,
        body=body,
    )
    print(f"  Status: created successfully")
    return result


def create_adls_scan(client, data_source_name: str) -> dict:
    """Create a scan for the ADLS Gen2 data source using managed identity."""
    scan_name = f"scan-lakehouse-weekly-{ENVIRONMENT}"

    body = {
        "kind": "AdlsGen2Msi",
        "properties": {
            "scanRulesetName": f"ruleset-lakehouse-{ENVIRONMENT}",
            "scanRulesetType": "Custom",
            "collection": {
                "type": "CollectionReference",
                "referenceName": ROOT_COLLECTION,
            },
        },
    }

    print(f"Creating scan: {scan_name}")
    print(f"  Data source: {data_source_name}")
    print(f"  Auth: Managed Identity (MSI)")

    result = client.scans.create_or_update(
        data_source_name=data_source_name,
        scan_name=scan_name,
        body=body,
    )
    print(f"  Status: created successfully")
    return result


def create_scan_trigger(client, data_source_name: str, scan_name: str) -> dict:
    """Set up weekly scan schedule (Sunday 2 AM UTC per LivaNova guidelines)."""
    body = {
        "properties": {
            "recurrence": {
                "frequency": SCAN_SCHEDULE_INTERVAL,
                "interval": 1,
                "startTime": "2026-03-02T02:00:00Z",
                "schedule": {
                    "weekDays": [SCAN_SCHEDULE_DAY],
                    "hours": [SCAN_SCHEDULE_HOUR],
                    "minutes": [0],
                },
            },
            "scanLevel": "Full",
        },
    }

    print(f"Creating scan trigger: {SCAN_SCHEDULE_INTERVAL} on {SCAN_SCHEDULE_DAY} at {SCAN_SCHEDULE_HOUR}:00 UTC")
    result = client.triggers.create_trigger(
        data_source_name=data_source_name,
        scan_name=scan_name,
        body=body,
    )
    print(f"  Status: schedule created")
    return result


def run_scan_now(client, data_source_name: str, scan_name: str) -> dict:
    """Trigger an immediate initial scan."""
    run_id = str(uuid.uuid4())

    print(f"Running initial scan: {scan_name}")
    print(f"  Run ID: {run_id}")

    result = client.scan_result.run_scan(
        data_source_name=data_source_name,
        scan_name=scan_name,
        run_id=run_id,
    )
    print(f"  Status: scan triggered")
    return result


def main():
    parser = argparse.ArgumentParser(description="Configure Purview scans")
    parser.add_argument("--run-now", action="store_true", help="Run initial scan immediately")
    parser.add_argument("--no-schedule", action="store_true", help="Skip schedule setup")
    args = parser.parse_args()

    client = get_scanning_client()
    data_source_name = f"adls-lakehouse-{ENVIRONMENT}"
    scan_name = f"scan-lakehouse-weekly-{ENVIRONMENT}"

    print("=" * 60)
    print("Configuring Purview scans")
    print("=" * 60)

    # Step 1: Create scan rule set
    create_scan_ruleset(client)

    # Step 2: Create scan
    create_adls_scan(client, data_source_name)

    # Step 3: Set up weekly schedule
    if not args.no_schedule:
        create_scan_trigger(client, data_source_name, scan_name)
    else:
        print("Skipping schedule setup (--no-schedule)")

    # Step 4: Run initial scan
    if args.run_now:
        run_scan_now(client, data_source_name, scan_name)
    else:
        print("\nTip: Use --run-now to trigger an initial scan immediately")

    print("\nScan configuration complete.")


if __name__ == "__main__":
    main()
