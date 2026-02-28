#!/usr/bin/env python3
"""
Upload synthetic data to ADLS Gen2 Lakehouse.

Uploads:
  - Parquet files to bronze/ container (ERP, CRM, IoT data)
  - RAG documents to rag-documents/ container (JSON, MD, CSV)

Authentication: Uses DefaultAzureCredential (works with `az login`).

Usage:
    python upload_to_lakehouse.py
    python upload_to_lakehouse.py --storage-account dpstlakedevXXXXX
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from config import OUTPUT_BRONZE, OUTPUT_RAG, CONTAINER_BRONZE, CONTAINER_RAG, STORAGE_ACCOUNT_NAME


def get_storage_account_name() -> str:
    """Get storage account name from config, env var, or Azure CLI."""
    name = STORAGE_ACCOUNT_NAME
    if name:
        return name

    # Try to auto-detect from Azure CLI
    print("Auto-detecting storage account name from Azure...")
    try:
        result = subprocess.run(
            ["az", "storage", "account", "list",
             "--resource-group", "dp-rg-dev",
             "--query", "[?tags.Purpose=='Lakehouse'].name | [0]",
             "-o", "tsv"],
            capture_output=True, text=True, check=True
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


class LakehouseUploader:
    """Uploads local synthetic data to ADLS Gen2."""

    def __init__(self, storage_account: str = ""):
        self.storage_account = storage_account or get_storage_account_name()
        self.account_url = f"https://{self.storage_account}.dfs.core.windows.net"
        self._client = None

    def _get_client(self):
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.storage.filedatalake import DataLakeServiceClient
            credential = DefaultAzureCredential()
            self._client = DataLakeServiceClient(
                account_url=self.account_url,
                credential=credential
            )
        return self._client

    def _upload_directory(self, local_dir: Path, container_name: str, remote_prefix: str = ""):
        """Upload all files from a local directory to ADLS Gen2."""
        client = self._get_client()
        fs_client = client.get_file_system_client(container_name)

        files = list(local_dir.rglob("*"))
        files = [f for f in files if f.is_file()]

        if not files:
            print(f"  No files found in {local_dir}")
            return 0

        uploaded = 0
        total_size = 0

        for file_path in files:
            relative = file_path.relative_to(local_dir)
            remote_path = f"{remote_prefix}/{relative}" if remote_prefix else str(relative)
            remote_path = remote_path.replace("\\", "/")

            dir_client = fs_client.get_directory_client(str(Path(remote_path).parent))
            try:
                dir_client.create_directory()
            except Exception:
                pass  # Directory may already exist

            file_client = dir_client.get_file_client(file_path.name)
            file_size = file_path.stat().st_size

            with open(file_path, "rb") as f:
                file_client.upload_data(f, overwrite=True)

            uploaded += 1
            total_size += file_size
            size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024*1024):.2f} MB"
            print(f"    [{uploaded}/{len(files)}] {remote_path} ({size_str})")

        return uploaded, total_size

    def upload_all(self):
        """Upload all generated data to the lakehouse."""
        print("=" * 60)
        print(f"Uploading to ADLS Gen2: {self.storage_account}")
        print("=" * 60)

        total_files = 0
        total_bytes = 0

        # Upload bronze data (Parquet files)
        if OUTPUT_BRONZE.exists():
            print(f"\nUploading bronze data to '{CONTAINER_BRONZE}' container...")
            count, size = self._upload_directory(OUTPUT_BRONZE, CONTAINER_BRONZE)
            total_files += count
            total_bytes += size
        else:
            print(f"WARNING: {OUTPUT_BRONZE} not found. Run generate_all.py first.")

        # Upload RAG documents
        if OUTPUT_RAG.exists():
            print(f"\nUploading RAG documents to '{CONTAINER_RAG}' container...")
            count, size = self._upload_directory(OUTPUT_RAG, CONTAINER_RAG)
            total_files += count
            total_bytes += size
        else:
            print(f"WARNING: {OUTPUT_RAG} not found. Run generate_all.py first.")

        print("\n" + "=" * 60)
        total_mb = total_bytes / (1024 * 1024)
        print(f"Upload complete: {total_files} files, {total_mb:.2f} MB total")
        print(f"Storage account: {self.storage_account}")
        print(f"Portal: https://portal.azure.com/#view/Microsoft_Azure_Storage/ContainerMenuBlade/~/overview")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Upload synthetic data to ADLS Gen2")
    parser.add_argument(
        "--storage-account", type=str, default="",
        help="ADLS Gen2 storage account name"
    )
    args = parser.parse_args()

    uploader = LakehouseUploader(storage_account=args.storage_account)
    uploader.upload_all()


if __name__ == "__main__":
    main()
