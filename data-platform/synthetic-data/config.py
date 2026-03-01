"""Configuration for synthetic data generation and upload."""

import os
from pathlib import Path

# ============================================================================
# Storage Account Configuration
# ============================================================================
# Set via environment variable or will be auto-detected from Azure CLI
STORAGE_ACCOUNT_NAME = os.environ.get("LAKEHOUSE_STORAGE_ACCOUNT", "")
CONTAINER_BRONZE = "bronze"
CONTAINER_RAG = "rag-documents"

# ============================================================================
# Output Directories (local)
# ============================================================================
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_BRONZE = OUTPUT_DIR / "bronze"
OUTPUT_RAG = OUTPUT_DIR / "rag-documents"

# ============================================================================
# Data Volume Configuration
# ============================================================================
VOLUMES = {
    # ERP - SAP SD (~1.08M rows)
    "kna1": 10_000,          # Customer Master
    "mara": 2_000,           # Material Master
    "mard": 6_000,           # Plant Stock (1-3 per material across plants)
    "vbak": 100_000,         # Sales Order Header (~4,167/month over 24 months)
    "vbap": 300_000,         # Sales Order Item (avg 3 items/order)
    "vbrk": 80_000,          # Billing Header (80% of orders billed)
    "vbrp": 240_000,         # Billing Item
    "likp": 85_000,          # Delivery Header (85% of orders delivered)
    "lips": 255_000,         # Delivery Item
    # CRM - Salesforce (~163K rows)
    "accounts": 10_000,
    "contacts": 30_000,
    "opportunities": 50_000,
    "leads": 40_000,
    "cases": 25_000,
    "products": 2_000,
    "pricebook_entries": 6_000,
    # IoT (~500K rows)
    "iot_telemetry": 500_000,
}

# ============================================================================
# Domain Configuration - Manufacturing + Sales
# ============================================================================
DATE_RANGE_START = "2024-01-01"
DATE_RANGE_END = "2025-12-31"
RANDOM_SEED = 42

# SAP organizational structure
SAP_SALES_ORGS = ["1000", "2000", "3000"]
SAP_DIST_CHANNELS = ["10", "20", "30"]
SAP_DIVISIONS = ["01", "02", "03"]
SAP_PLANTS = ["1100", "1200", "2100", "2200", "3100"]
SAP_STORAGE_LOCATIONS = ["0001", "0002", "0003", "0010"]
SAP_SHIPPING_POINTS = ["1100", "1200", "2100"]
SAP_DOC_TYPES = ["ZOR", "ZRE", "ZCR", "ZDR", "ZQT"]
SAP_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD"]

# Material groups for manufacturing
MATERIAL_GROUPS = {
    "001": "Steel & Metal Products",
    "002": "Bearings & Bushings",
    "003": "Electric Motors",
    "004": "Hydraulic Components",
    "005": "Pneumatic Components",
    "006": "Fasteners & Hardware",
    "007": "Seals & Gaskets",
    "008": "Pumps & Valves",
    "009": "Sensors & Instrumentation",
    "010": "Industrial Chemicals",
}

MATERIAL_TYPES = ["FERT", "HALB", "ROH", "HIBE", "ERSA"]

# Salesforce-specific
SF_INDUSTRIES = [
    "Manufacturing", "Automotive", "Aerospace", "Energy",
    "Construction", "Mining", "Food & Beverage", "Pharmaceuticals",
    "Chemical", "Electronics", "Packaging", "Metals",
]
SF_LEAD_SOURCES = [
    "Web", "Trade Show", "Referral", "Partner",
    "Cold Call", "Advertisement", "Email Campaign",
]
SF_OPPORTUNITY_STAGES = [
    "Prospecting", "Qualification", "Needs Analysis",
    "Value Proposition", "Negotiation", "Closed Won", "Closed Lost",
]
SF_CASE_PRIORITIES = ["Low", "Medium", "High", "Critical"]
SF_CASE_TYPES = [
    "Technical Support", "Quality Issue", "Delivery Delay",
    "Pricing Inquiry", "Return/RMA", "Installation Support",
]

# IoT configuration
IOT_DEVICE_COUNT = 200
IOT_DEVICE_TYPES = ["temperature", "pressure", "vibration", "humidity", "flow_rate", "power"]
IOT_PRODUCTION_LINES = ["LINE-A", "LINE-B", "LINE-C", "LINE-D"]

# ============================================================================
# RAG Chunking Configuration (used by chunk_for_rag.py)
# ============================================================================
RAG_LARGE_ORDER_THRESHOLD = 50_000   # Orders > $50K get individual RAG docs
RAG_RECENT_MONTHS = 6                # Orders in last N months get individual docs
RAG_CUSTOMER_PROFILES = "all"        # "all" or integer for top-N by revenue
