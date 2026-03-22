#!/usr/bin/env python3
"""Massive OpenAPI Ingestion - Ingest ALL available specs.

Scans the konfig-sdks/openapi-examples directory and ingests
EVERY available OpenAPI specification.

This is the nuclear option for maximum API coverage.
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Generator

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from me4brain.retrieval.openapi_ingester import OpenAPIIngester


def find_all_openapi_specs(base_dir: Path) -> Generator[tuple[str, Path], None, None]:
    """Find all OpenAPI spec files in the directory tree."""
    patterns = ["openapi.yaml", "openapi.yml", "openapi.json", "spec.yaml", "spec.json"]

    for root, dirs, files in os.walk(base_dir):
        # Skip hidden directories and common non-API dirs
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]

        for pattern in patterns:
            if pattern in files:
                api_name = Path(root).name
                yield (api_name, Path(root) / pattern)
                break  # Only take first matching file per directory


async def massive_ingest():
    """Ingest ALL OpenAPI specs from konfig-sdks."""
    print("🚀 MASSIVE OpenAPI Ingestion")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent / "data" / "openapi-examples"
    if not base_dir.exists():
        print(f"❌ Directory not found: {base_dir}")
        return []

    # Collect all specs
    all_specs = list(find_all_openapi_specs(base_dir))
    print(f"📂 Found {len(all_specs)} OpenAPI specifications\n")

    ingester = OpenAPIIngester()
    tenant_id = "me4brain_core"

    total_tools = 0
    success_count = 0
    failed = []

    for i, (api_name, spec_path) in enumerate(all_specs, 1):
        try:
            print(f"[{i}/{len(all_specs)}] {api_name}...", end=" ", flush=True)

            tools = await ingester.ingest_from_file(
                tenant_id=tenant_id,
                file_path=spec_path,
                api_prefix=api_name.replace("-", "_"),
            )

            count = len(tools)
            total_tools += count
            success_count += 1
            print(f"✅ {count} tools")

        except Exception as e:
            error_msg = str(e)[:50]
            print(f"❌ {error_msg}")
            failed.append((api_name, error_msg))

    # Summary
    print("\n" + "=" * 60)
    print("📊 MASSIVE INGESTION COMPLETE")
    print(f"  • APIs Processed: {len(all_specs)}")
    print(f"  • Successful: {success_count}")
    print(f"  • Failed: {len(failed)}")
    print(f"  • Total Tools Created: {total_tools}")

    if failed and len(failed) <= 20:
        print("\n❌ Failed APIs:")
        for name, error in failed[:20]:
            print(f"  • {name}: {error}")

    return total_tools


if __name__ == "__main__":
    asyncio.run(massive_ingest())
