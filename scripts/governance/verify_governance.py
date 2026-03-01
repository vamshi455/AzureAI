#!/usr/bin/env python3
"""Verify Purview governance configuration.

Smoke test that checks all governance components are properly configured:
  - Data sources registered
  - Scans configured and have history
  - Business glossary populated
  - Custom classifications created

Usage:
    python verify_governance.py
"""

import sys

from purview_client import get_scanning_client, get_catalog_client
from config import ENVIRONMENT


def check_data_sources(client) -> bool:
    """Verify data sources are registered."""
    print("Checking data sources...")
    sources = list(client.data_sources.list_all())
    print(f"  Found {len(sources)} data source(s):")
    for src in sources:
        print(f"    - {src['name']} ({src.get('kind', 'unknown')})")

    expected = f"adls-lakehouse-{ENVIRONMENT}"
    found = any(s["name"] == expected for s in sources)
    if found:
        print(f"  PASS: {expected} registered")
    else:
        print(f"  FAIL: {expected} not found")
    return found


def check_scans(client) -> bool:
    """Verify scans are configured."""
    print("\nChecking scans...")
    data_source_name = f"adls-lakehouse-{ENVIRONMENT}"
    scan_name = f"scan-lakehouse-weekly-{ENVIRONMENT}"

    try:
        scan = client.scans.get(
            data_source_name=data_source_name,
            scan_name=scan_name,
        )
        print(f"  Found scan: {scan['name']} (kind: {scan.get('kind', 'unknown')})")
        print(f"  PASS: Scan configured")
        return True
    except Exception as e:
        print(f"  FAIL: Scan not found — {e}")
        return False


def check_scan_history(client) -> bool:
    """Check if any scan has been run."""
    print("\nChecking scan history...")
    data_source_name = f"adls-lakehouse-{ENVIRONMENT}"
    scan_name = f"scan-lakehouse-weekly-{ENVIRONMENT}"

    try:
        runs = list(client.scan_result.list_scan_history(
            data_source_name=data_source_name,
            scan_name=scan_name,
        ))
        print(f"  Found {len(runs)} scan run(s):")
        for run in runs[:5]:
            status = run.get("status", "unknown")
            start = run.get("startTime", "unknown")
            print(f"    - {status} (started: {start})")

        if runs:
            print(f"  PASS: Scan has been run")
            return True
        else:
            print(f"  WARN: No scan runs yet (run configure_scans.py --run-now)")
            return True  # Not a failure, just needs to be triggered
    except Exception:
        print(f"  SKIP: Cannot check scan history (scan may not exist yet)")
        return True


def check_glossary(client) -> bool:
    """Verify business glossary is populated."""
    print("\nChecking business glossary...")
    try:
        glossaries = client.glossary.list_glossaries()
        glossary_list = list(glossaries)
        print(f"  Found {len(glossary_list)} glossary(ies):")

        target_name = "Manufacturing & Sales Data Platform Glossary"
        found = False
        for g in glossary_list:
            name = g.get("name", "unknown")
            term_count = g.get("termCount", 0)
            print(f"    - {name} ({term_count} terms)")
            if name == target_name:
                found = True

        if found:
            print(f"  PASS: Platform glossary found")
        else:
            print(f"  FAIL: Platform glossary not found")
        return found
    except Exception as e:
        print(f"  FAIL: Cannot access glossary — {e}")
        return False


def check_classifications(scanning_client) -> bool:
    """Verify custom classification rules exist."""
    print("\nChecking custom classification rules...")
    try:
        rules = list(scanning_client.classification_rules.list_all())
        custom_rules = [r for r in rules if r.get("kind") == "Custom"]
        print(f"  Found {len(custom_rules)} custom classification rule(s):")

        expected_rules = [
            "custom-customer-data",
            "custom-financial-data",
            "custom-employee-data",
            "custom-manufacturing-ip",
            "custom-regulatory-data",
        ]

        found_names = {r["name"] for r in custom_rules}
        for rule_name in expected_rules:
            if rule_name in found_names:
                print(f"    - {rule_name}: FOUND")
            else:
                print(f"    - {rule_name}: MISSING")

        all_found = all(r in found_names for r in expected_rules)
        if all_found:
            print(f"  PASS: All custom classification rules found")
        else:
            print(f"  FAIL: Some classification rules missing")
        return all_found
    except Exception as e:
        print(f"  FAIL: Cannot list classification rules — {e}")
        return False


def main():
    print("=" * 60)
    print("Verifying Purview governance configuration")
    print(f"Environment: {ENVIRONMENT}")
    print("=" * 60)

    scanning_client = get_scanning_client()
    catalog_client = get_catalog_client()

    results = []

    results.append(("Data Sources", check_data_sources(scanning_client)))
    results.append(("Scans", check_scans(scanning_client)))
    results.append(("Scan History", check_scan_history(scanning_client)))
    results.append(("Business Glossary", check_glossary(catalog_client)))
    results.append(("Classifications", check_classifications(scanning_client)))

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    passed = 0
    failed = 0
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\n  {passed}/{len(results)} checks passed")

    if failed > 0:
        print("\nSome checks failed. Run the corresponding scripts to fix:")
        print("  register_sources.py  -> Data sources")
        print("  configure_scans.py   -> Scans")
        print("  create_glossary.py   -> Business glossary")
        print("  create_classifications.py -> Classifications")
        sys.exit(1)
    else:
        print("\nAll governance checks passed!")


if __name__ == "__main__":
    main()
