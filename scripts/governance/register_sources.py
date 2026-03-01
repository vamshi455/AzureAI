#!/usr/bin/env python3
"""Register data sources in Microsoft Purview.

Registers the ADLS Gen2 lakehouse as a data source using the
PurviewScanningClient. Idempotent — creates if not exists, updates if exists.

Usage:
    python register_sources.py
    python register_sources.py --storage-account dpstlakedevXXXXX
"""

import argparse
import subprocess
import sys

from purview_client import get_scanning_client, get_storage_account_name
from config import ENVIRONMENT, RESOURCE_GROUP, ROOT_COLLECTION, SUBSCRIPTION_ID


def get_subscription_id() -> str:
    """Get Azure subscription ID from config or auto-detect via Azure CLI."""
    if SUBSCRIPTION_ID:
        return SUBSCRIPTION_ID

    print("Auto-detecting subscription ID from Azure CLI...")
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "id", "-o", "tsv"],
            capture_output=True, text=True, check=True,
        )
        sub_id = result.stdout.strip()
        if sub_id:
            print(f"  Found: {sub_id}")
            return sub_id
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    print("ERROR: Could not determine subscription ID.")
    print("Set AZURE_SUBSCRIPTION_ID env var or ensure `az login` is configured.")
    sys.exit(1)


def register_adls_gen2(client, storage_account: str, subscription_id: str) -> dict:
    """Register ADLS Gen2 lakehouse as a Purview data source."""
    data_source_name = f"adls-lakehouse-{ENVIRONMENT}"

    body = {
        "kind": "AdlsGen2",
        "properties": {
            "endpoint": f"https://{storage_account}.dfs.core.windows.net",
            "subscriptionId": subscription_id,
            "resourceGroup": RESOURCE_GROUP,
            "location": "eastus2",
            "resourceName": storage_account,
            "collection": {
                "type": "CollectionReference",
                "referenceName": ROOT_COLLECTION,
            },
        },
    }

    print(f"Registering data source: {data_source_name}")
    print(f"  Storage account: {storage_account}")
    print(f"  Endpoint: {body['properties']['endpoint']}")

    result = client.data_sources.create_or_update(
        data_source_name=data_source_name,
        body=body,
    )
    print(f"  Status: registered successfully")
    return result


def register_postgresql(client, subscription_id: str) -> dict:
    """Register PostgreSQL Flexible Server as a Purview data source."""
    data_source_name = f"postgresql-vector-{ENVIRONMENT}"
    server_name = f"dp-psql-vector-{ENVIRONMENT}-eus2"

    body = {
        "kind": "AzurePostgreSql",
        "properties": {
            "serverEndpoint": f"{server_name}.postgres.database.azure.com",
            "subscriptionId": subscription_id,
            "resourceGroup": RESOURCE_GROUP,
            "location": "eastus2",
            "resourceName": server_name,
            "port": 5432,
            "collection": {
                "type": "CollectionReference",
                "referenceName": ROOT_COLLECTION,
            },
        },
    }

    print(f"Registering data source: {data_source_name}")
    print(f"  Server: {server_name}")

    result = client.data_sources.create_or_update(
        data_source_name=data_source_name,
        body=body,
    )
    print(f"  Status: registered successfully")
    return result


def list_registered_sources(client) -> list:
    """List all registered data sources."""
    sources = list(client.data_sources.list_all())
    print(f"\nRegistered data sources ({len(sources)}):")
    for src in sources:
        kind = src.get("kind", "unknown")
        name = src.get("name", "unknown")
        print(f"  - {name} ({kind})")
    return sources


def main():
    parser = argparse.ArgumentParser(description="Register data sources in Purview")
    parser.add_argument("--storage-account", help="ADLS Gen2 storage account name")
    args = parser.parse_args()

    storage_account = args.storage_account or get_storage_account_name()
    subscription_id = get_subscription_id()

    client = get_scanning_client()

    print("=" * 60)
    print("Registering data sources in Microsoft Purview")
    print("=" * 60)

    # Register ADLS Gen2 lakehouse
    register_adls_gen2(client, storage_account, subscription_id)

    # Register PostgreSQL (vector database)
    register_postgresql(client, subscription_id)

    # List all registered sources
    list_registered_sources(client)

    print("\nData source registration complete.")


if __name__ == "__main__":
    main()
