#!/usr/bin/env python3
"""Create business glossary in Microsoft Purview.

Creates a Manufacturing & Sales business glossary with categories and terms
that map SAP technical field names, Salesforce entities, and IoT concepts
to business-friendly definitions.

Follows the LivaNova Fabric Development Framework glossary best practices:
- Map technical metadata to business-friendly terms
- Link terms to data assets
- Flag PII-containing fields

Usage:
    python create_glossary.py
    python create_glossary.py --dry-run   # preview without creating
"""

import argparse
import json
import sys

from purview_client import get_catalog_client
from config import GLOSSARY_TERMS_FILE


def load_glossary_data() -> dict:
    """Load glossary definitions from JSON data file."""
    if not GLOSSARY_TERMS_FILE.exists():
        print(f"ERROR: Glossary data file not found: {GLOSSARY_TERMS_FILE}")
        sys.exit(1)

    with open(GLOSSARY_TERMS_FILE) as f:
        return json.load(f)


def get_existing_glossaries(client) -> dict:
    """Get existing glossaries, keyed by name."""
    glossaries = client.glossary.list_glossaries()
    return {g["name"]: g for g in glossaries}


def create_or_get_glossary(client, glossary_config: dict, dry_run: bool = False) -> dict:
    """Create the glossary if it doesn't exist, or return existing."""
    existing = get_existing_glossaries(client)

    if glossary_config["name"] in existing:
        glossary = existing[glossary_config["name"]]
        print(f"Glossary already exists: {glossary['name']} (guid: {glossary['guid']})")
        return glossary

    if dry_run:
        print(f"[DRY RUN] Would create glossary: {glossary_config['name']}")
        return {"guid": "dry-run", "name": glossary_config["name"]}

    body = {
        "name": glossary_config["name"],
        "qualifiedName": glossary_config["qualifiedName"],
        "shortDescription": glossary_config["shortDescription"],
    }

    result = client.glossary.create_glossary(body)
    print(f"Created glossary: {result['name']} (guid: {result['guid']})")
    return result


def get_existing_categories(client, glossary_guid: str) -> dict:
    """Get existing categories for a glossary, keyed by name."""
    try:
        categories = client.glossary.list_glossary_categories(glossary_guid)
        return {c["name"]: c for c in categories}
    except Exception:
        return {}


def create_or_get_category(client, glossary_guid: str, category_config: dict, dry_run: bool = False) -> dict:
    """Create a glossary category if it doesn't exist."""
    existing = get_existing_categories(client, glossary_guid)

    if category_config["name"] in existing:
        cat = existing[category_config["name"]]
        print(f"  Category exists: {cat['name']}")
        return cat

    if dry_run:
        print(f"  [DRY RUN] Would create category: {category_config['name']}")
        return {"guid": "dry-run", "name": category_config["name"]}

    body = {
        "name": category_config["name"],
        "shortDescription": category_config["shortDescription"],
        "anchor": {"glossaryGuid": glossary_guid},
    }

    result = client.glossary.create_glossary_category(body)
    print(f"  Created category: {result['name']} (guid: {result['guid']})")
    return result


def get_existing_terms(client, glossary_guid: str) -> dict:
    """Get existing glossary terms, keyed by name."""
    try:
        terms = client.glossary.list_glossary_terms(glossary_guid)
        return {t["name"]: t for t in terms}
    except Exception:
        return {}


def create_or_update_term(
    client,
    glossary_guid: str,
    category_guid: str,
    term_config: dict,
    existing_terms: dict,
    dry_run: bool = False,
) -> dict:
    """Create a glossary term if it doesn't exist."""
    if term_config["name"] in existing_terms:
        print(f"    Term exists: {term_config['name']}")
        return existing_terms[term_config["name"]]

    if dry_run:
        pii_flag = " [PII]" if term_config.get("pii") else ""
        print(f"    [DRY RUN] Would create term: {term_config['name']}{pii_flag}")
        return {"guid": "dry-run", "name": term_config["name"]}

    body = {
        "name": term_config["name"],
        "qualifiedName": f"ManufacturingSalesGlossary@{term_config['name']}",
        "shortDescription": term_config["shortDescription"],
        "longDescription": term_config.get("longDescription", ""),
        "status": term_config.get("status", "Draft"),
        "anchor": {"glossaryGuid": glossary_guid},
    }

    # Add abbreviation as attribute if present
    if term_config.get("abbreviation"):
        body["abbreviation"] = term_config["abbreviation"]

    # Add category assignment
    if category_guid and category_guid != "dry-run":
        body["categories"] = [{"categoryGuid": category_guid}]

    result = client.glossary.create_glossary_term(body)
    pii_flag = " [PII]" if term_config.get("pii") else ""
    print(f"    Created term: {result['name']}{pii_flag} (guid: {result['guid']})")
    return result


def main():
    parser = argparse.ArgumentParser(description="Create Purview business glossary")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    data = load_glossary_data()
    glossary_config = data["glossary"]
    categories_config = data["categories"]
    terms_config = data["terms"]

    print("=" * 60)
    print("Creating business glossary in Microsoft Purview")
    print("=" * 60)
    print(f"Glossary: {glossary_config['name']}")
    print(f"Categories: {len(categories_config)}")
    print(f"Terms: {len(terms_config)}")
    if args.dry_run:
        print("[DRY RUN MODE — no changes will be made]")
    print()

    if args.dry_run:
        client = None
        glossary_guid = "dry-run"
    else:
        client = get_catalog_client()
        glossary = create_or_get_glossary(client, glossary_config, args.dry_run)
        glossary_guid = glossary["guid"]

    # Create categories
    print("\nCategories:")
    category_guids = {}
    for cat_config in categories_config:
        if args.dry_run:
            print(f"  [DRY RUN] Would create category: {cat_config['name']}")
            category_guids[cat_config["name"]] = "dry-run"
        else:
            cat = create_or_get_category(client, glossary_guid, cat_config, args.dry_run)
            category_guids[cat_config["name"]] = cat["guid"]

    # Create terms
    print("\nTerms:")
    if not args.dry_run:
        existing_terms = get_existing_terms(client, glossary_guid)
    else:
        existing_terms = {}

    pii_count = 0
    for term_config in terms_config:
        cat_guid = category_guids.get(term_config.get("category", ""), "")
        create_or_update_term(client, glossary_guid, cat_guid, term_config, existing_terms, args.dry_run)
        if term_config.get("pii"):
            pii_count += 1

    # Summary
    print(f"\nGlossary creation complete:")
    print(f"  Total terms: {len(terms_config)}")
    print(f"  PII terms: {pii_count}")
    print(f"  Categories: {len(categories_config)}")


if __name__ == "__main__":
    main()
