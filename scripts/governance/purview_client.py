"""Authenticated Purview client factory.

Uses DefaultAzureCredential following the pattern from
data-platform/synthetic-data/upload_to_lakehouse.py.
Works with `az login` for local development and managed identity in Azure.
"""

import subprocess
import sys

from azure.identity import DefaultAzureCredential
from azure.purview.scanning import PurviewScanningClient
from azure.purview.catalog import PurviewCatalogClient

from config import (
    PURVIEW_SCAN_ENDPOINT,
    PURVIEW_CATALOG_ENDPOINT,
    LAKEHOUSE_STORAGE_ACCOUNT,
    RESOURCE_GROUP,
)

_credential = None


def get_credential() -> DefaultAzureCredential:
    """Get or create a shared DefaultAzureCredential instance."""
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def get_scanning_client() -> PurviewScanningClient:
    """Create a PurviewScanningClient for data source and scan management."""
    return PurviewScanningClient(
        endpoint=PURVIEW_SCAN_ENDPOINT,
        credential=get_credential(),
    )


def get_catalog_client() -> PurviewCatalogClient:
    """Create a PurviewCatalogClient for glossary, classification, and catalog ops."""
    return PurviewCatalogClient(
        endpoint=PURVIEW_CATALOG_ENDPOINT,
        credential=get_credential(),
    )


def get_storage_account_name() -> str:
    """Get ADLS Gen2 storage account name from config or auto-detect via Azure CLI."""
    if LAKEHOUSE_STORAGE_ACCOUNT:
        return LAKEHOUSE_STORAGE_ACCOUNT

    print("Auto-detecting storage account name from Azure...")
    try:
        result = subprocess.run(
            [
                "az", "storage", "account", "list",
                "--resource-group", RESOURCE_GROUP,
                "--query", "[?tags.Purpose=='Lakehouse'].name | [0]",
                "-o", "tsv",
            ],
            capture_output=True, text=True, check=True,
        )
        name = result.stdout.strip()
        if name:
            print(f"  Found: {name}")
            return name
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    print("ERROR: Could not determine storage account name.")
    print("Set LAKEHOUSE_STORAGE_ACCOUNT env var or pass --storage-account")
    sys.exit(1)
