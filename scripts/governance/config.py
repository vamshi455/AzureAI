"""Configuration for Purview governance scripts.

Follows the pattern from data-platform/synthetic-data/config.py.
All values can be overridden via environment variables.
"""

import os
from pathlib import Path

# ============================================================================
# Purview Account Configuration
# ============================================================================
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PURVIEW_ACCOUNT_NAME = os.environ.get("PURVIEW_ACCOUNT_NAME", f"dp-pview-{ENVIRONMENT}")
PURVIEW_SCAN_ENDPOINT = os.environ.get(
    "PURVIEW_SCAN_ENDPOINT",
    f"https://{PURVIEW_ACCOUNT_NAME}.scan.purview.azure.com",
)
PURVIEW_CATALOG_ENDPOINT = os.environ.get(
    "PURVIEW_CATALOG_ENDPOINT",
    f"https://{PURVIEW_ACCOUNT_NAME}.purview.azure.com",
)

# ============================================================================
# Azure Resource Configuration
# ============================================================================
RESOURCE_GROUP = os.environ.get("RESOURCE_GROUP", f"dp-rg-{ENVIRONMENT}")
SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
LAKEHOUSE_STORAGE_ACCOUNT = os.environ.get("LAKEHOUSE_STORAGE_ACCOUNT", "")

# ADLS Gen2 containers to scan
ADLS_CONTAINERS = ["bronze", "silver", "gold", "rag-documents"]

# ============================================================================
# Collection Names (Purview hierarchy)
# ============================================================================
ROOT_COLLECTION = PURVIEW_ACCOUNT_NAME
COLLECTION_MANUFACTURING = "Manufacturing"
COLLECTION_SALES = "Sales"
COLLECTION_IOT = "IoT"

# ============================================================================
# Scan Schedule (per LivaNova guidelines: weekly PII detection)
# ============================================================================
SCAN_SCHEDULE_INTERVAL = "Week"
SCAN_SCHEDULE_DAY = "Sunday"
SCAN_SCHEDULE_HOUR = 2  # 2:00 AM UTC

# ============================================================================
# Governance Data Files
# ============================================================================
DATA_DIR = Path(__file__).parent / "data"
GLOSSARY_TERMS_FILE = DATA_DIR / "glossary_terms.json"
CLASSIFICATION_RULES_FILE = DATA_DIR / "classification_rules.json"
