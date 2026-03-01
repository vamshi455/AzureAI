#!/usr/bin/env python3
"""Create custom classifications and classification rules in Microsoft Purview.

Implements the LivaNova Framework's custom classification taxonomy:
  - CUSTOM_CUSTOMER_DATA (GDPR subject rights)
  - CUSTOM_FINANCIAL_DATA (SOX compliance)
  - CUSTOM_EMPLOYEE_DATA (internal privacy)
  - CUSTOM_MANUFACTURING_IP (competitive protection)
  - CUSTOM_REGULATORY_DATA (FDA/SEC/EMA audit trails)

Also lists built-in Sensitive Information Types (SITs) to enable in scan rule sets.

Usage:
    python create_classifications.py
    python create_classifications.py --dry-run   # preview without creating
"""

import argparse
import json
import sys

from purview_client import get_catalog_client, get_scanning_client
from config import CLASSIFICATION_RULES_FILE


def load_classification_data() -> dict:
    """Load classification definitions from JSON data file."""
    if not CLASSIFICATION_RULES_FILE.exists():
        print(f"ERROR: Classification data file not found: {CLASSIFICATION_RULES_FILE}")
        sys.exit(1)

    with open(CLASSIFICATION_RULES_FILE) as f:
        return json.load(f)


def create_custom_classification_type(catalog_client, classification: dict, dry_run: bool = False) -> dict:
    """Create a custom classification type definition in Purview via Atlas v2 API."""
    name = classification["name"]

    if dry_run:
        print(f"  [DRY RUN] Would create classification type: {name}")
        return {"name": name}

    type_def = {
        "classificationDefs": [
            {
                "name": name,
                "description": classification["description"],
                "attributeDefs": [],
            }
        ]
    }

    try:
        result = catalog_client.types.create_type_definitions(type_def)
        print(f"  Created classification type: {name}")
        return result
    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg.lower() or "ATLAS-409" in error_msg:
            print(f"  Classification type already exists: {name}")
            return {"name": name}
        raise


def create_classification_rule(scanning_client, classification: dict, dry_run: bool = False) -> dict:
    """Create a classification rule with column regex patterns."""
    rule_name = classification["name"].lower().replace("_", "-")

    if dry_run:
        patterns = [cp["pattern"] for cp in classification["columnPatterns"]]
        print(f"  [DRY RUN] Would create rule: {rule_name}")
        print(f"            Patterns: {len(patterns)}")
        return {"name": rule_name}

    body = {
        "kind": "Custom",
        "properties": {
            "description": classification["description"],
            "classificationName": classification["name"],
            "ruleStatus": "Enabled",
            "columnPatterns": [
                {
                    "kind": "Regex",
                    "pattern": cp["pattern"],
                }
                for cp in classification["columnPatterns"]
            ],
        },
    }

    try:
        result = scanning_client.classification_rules.create_or_update(
            classification_rule_name=rule_name,
            body=body,
        )
        pattern_count = len(classification["columnPatterns"])
        print(f"  Created classification rule: {rule_name} ({pattern_count} patterns)")
        return result
    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg.lower():
            print(f"  Classification rule already exists: {rule_name}")
            return {"name": rule_name}
        raise


def main():
    parser = argparse.ArgumentParser(description="Create Purview custom classifications")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    data = load_classification_data()
    custom_classifications = data["custom_classifications"]
    built_in_sits = data["built_in_classifications_to_enable"]

    print("=" * 60)
    print("Creating custom classifications in Microsoft Purview")
    print("=" * 60)
    print(f"Custom classifications: {len(custom_classifications)}")
    print(f"Built-in SITs to reference: {len(built_in_sits)}")
    if args.dry_run:
        print("[DRY RUN MODE — no changes will be made]")
    print()

    if args.dry_run:
        catalog_client = None
        scanning_client = None
    else:
        catalog_client = get_catalog_client()
        scanning_client = get_scanning_client()

    # Step 1: Create custom classification type definitions
    print("Step 1: Creating classification type definitions...")
    for classification in custom_classifications:
        create_custom_classification_type(catalog_client, classification, args.dry_run)

    # Step 2: Create classification rules with column patterns
    print("\nStep 2: Creating classification rules...")
    for classification in custom_classifications:
        create_classification_rule(scanning_client, classification, args.dry_run)

    # Step 3: List built-in SITs (informational)
    print("\nStep 3: Built-in Sensitive Information Types (enabled by default in scans):")
    for sit in built_in_sits:
        friendly_name = sit.replace("MICROSOFT.", "").replace(".", " > ").replace("_", " ").title()
        print(f"  - {friendly_name}")

    # Summary
    total_patterns = sum(len(c["columnPatterns"]) for c in custom_classifications)
    print(f"\nClassification setup complete:")
    print(f"  Custom types: {len(custom_classifications)}")
    print(f"  Classification rules: {len(custom_classifications)}")
    print(f"  Total column patterns: {total_patterns}")
    print(f"  Built-in SITs: {len(built_in_sits)}")
    print("\nNote: Re-run scans after creating classification rules to apply them to existing assets.")


if __name__ == "__main__":
    main()
