#!/usr/bin/env python3
"""Orchestrate all Purview governance configuration scripts.

Runs all governance scripts in the correct order:
  1. Register data sources (ADLS Gen2, PostgreSQL)
  2. Configure scans (rule set, scan, weekly schedule, initial run)
  3. Create business glossary (4 categories, 20 terms)
  4. Create custom classifications (5 custom + 7 built-in SITs)
  5. Verify all configuration

Usage:
    python run_all.py
    python run_all.py --dry-run        # preview all steps
    python run_all.py --skip-verify    # skip verification step
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def run_step(step_num: int, total: int, description: str, script: str, extra_args: list = None):
    """Run a governance script as a subprocess."""
    print(f"\n{'=' * 60}")
    print(f"Step {step_num}/{total}: {description}")
    print(f"{'=' * 60}")

    cmd = [sys.executable, str(SCRIPT_DIR / script)]
    if extra_args:
        cmd.extend(extra_args)

    start = time.time()
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\nERROR: Step {step_num} failed (exit code {result.returncode})")
        print(f"Script: {script}")
        sys.exit(result.returncode)

    print(f"\nStep {step_num} completed in {elapsed:.1f}s")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run all Purview governance configuration")
    parser.add_argument("--dry-run", action="store_true", help="Preview all steps without making changes")
    parser.add_argument("--skip-verify", action="store_true", help="Skip verification step")
    parser.add_argument("--storage-account", help="ADLS Gen2 storage account name")
    args = parser.parse_args()

    total_steps = 4 if args.skip_verify else 5
    extra = []
    if args.dry_run:
        extra.append("--dry-run")

    print("=" * 60)
    print("Purview Governance Configuration — Full Setup")
    print("=" * 60)
    if args.dry_run:
        print("[DRY RUN MODE — no changes will be made]")
    print(f"Total steps: {total_steps}")

    start_total = time.time()

    # Step 1: Register data sources
    register_args = []
    if args.storage_account:
        register_args.extend(["--storage-account", args.storage_account])
    run_step(1, total_steps, "Register data sources", "register_sources.py", register_args)

    # Step 2: Configure scans
    scan_args = ["--run-now"]
    run_step(2, total_steps, "Configure scans and run initial scan", "configure_scans.py", scan_args)

    # Step 3: Create business glossary
    run_step(3, total_steps, "Create business glossary", "create_glossary.py", extra)

    # Step 4: Create custom classifications
    run_step(4, total_steps, "Create custom classifications", "create_classifications.py", extra)

    # Step 5: Verify
    if not args.skip_verify:
        run_step(5, total_steps, "Verify governance configuration", "verify_governance.py")

    elapsed_total = time.time() - start_total
    print(f"\n{'=' * 60}")
    print(f"All {total_steps} steps completed in {elapsed_total:.1f}s")
    print(f"{'=' * 60}")

    print("\nNext steps (manual — see documentation/runbooks/purview-governance.md):")
    print("  1. Configure sensitivity labels in Microsoft Purview Compliance Portal")
    print("  2. Configure DLP policies in Microsoft Purview Compliance Portal")
    print("  3. Review initial scan results in Purview Data Map")


if __name__ == "__main__":
    main()
