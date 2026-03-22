#!/usr/bin/env python3
"""Batch API Ingestion Script.

Ingests priority OpenAPI specs into Me4BrAIn's Dynamic API Store.
Uses the existing OpenAPIIngester infrastructure.
"""

import asyncio
import json
import yaml
from pathlib import Path
from dataclasses import dataclass

# Import Me4BrAIn components
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from me4brain.retrieval.openapi_ingester import OpenAPIIngester, create_openapi_ingester


@dataclass
class APISpec:
    """Represents an API to ingest."""

    name: str
    category: str
    path: Path
    priority: int = 1  # 1 = highest


# Priority APIs to ingest
PRIORITY_APIS = [
    # Testing & Utility (No Auth - Perfect for validation)
    APISpec("httpbin", "utility", Path("data/openapi-examples/httpbin/openapi.yaml"), 1),
    # Space & Science
    APISpec(
        "nasa-techport", "science", Path("data/openapi-examples/nasa/tech-port/openapi.yaml"), 1
    ),
    # Knowledge & Media
    APISpec("wikimedia", "knowledge", Path("data/openapi-examples/wikimedia/openapi.yaml"), 2),
    APISpec("spotify", "media", Path("data/openapi-examples/spotify/openapi.yaml"), 3),
    APISpec("giphy", "media", Path("data/openapi-examples/giphy/openapi.yaml"), 3),
    # LLM & AI
    APISpec("langfuse", "ai", Path("data/openapi-examples/langfuse/openapi.yaml"), 2),
    APISpec("elevenlabs", "ai", Path("data/openapi-examples/elevenlabs/openapi.yaml"), 3),
    # Finance & Payments
    APISpec(
        "klarna-checkout", "finance", Path("data/openapi-examples/klarna/checkout/openapi.yaml"), 3
    ),
    APISpec("paypal", "finance", Path("data/openapi-examples/paypal/invoicing/openapi.yaml"), 3),
    # Communication
    APISpec("postmark", "communication", Path("data/openapi-examples/postmark/openapi.yaml"), 2),
    APISpec("sendgrid", "communication", Path("data/openapi-examples/sendgrid/openapi.yaml"), 3),
    APISpec("slack", "communication", Path("data/openapi-examples/slack/openapi.yaml"), 2),
    # HR & Business
    APISpec("notion", "productivity", Path("data/openapi-examples/notion/openapi.yaml"), 2),
    APISpec("asana", "productivity", Path("data/openapi-examples/asana/openapi.yaml"), 3),
    APISpec("trello", "productivity", Path("data/openapi-examples/trello/openapi.yaml"), 3),
]

# Default tenant for API Store
DEFAULT_TENANT = "me4brain_core"


def load_spec(spec_path: Path) -> dict | None:
    """Load an OpenAPI spec from file."""
    if not spec_path.exists():
        print(f"  ⚠️  File not found: {spec_path}")
        return None

    try:
        with open(spec_path, "r") as f:
            if spec_path.suffix == ".yaml" or spec_path.suffix == ".yml":
                return yaml.safe_load(f)
            else:
                return json.load(f)
    except Exception as e:
        print(f"  ❌ Error loading {spec_path}: {e}")
        return None


async def ingest_api(ingester: OpenAPIIngester, api: APISpec) -> list[str]:
    """Ingest a single API spec."""
    print(f"\n📥 Ingesting: {api.name} ({api.category})")

    spec = load_spec(api.path)
    if not spec:
        return []

    try:
        tool_ids = await ingester.ingest_from_dict(
            tenant_id=DEFAULT_TENANT,
            spec=spec,
            api_prefix=api.name,
        )
        print(f"  ✅ Created {len(tool_ids)} tools")
        return tool_ids
    except Exception as e:
        print(f"  ❌ Ingestion failed: {e}")
        return []


async def main():
    """Main entry point."""
    print("🚀 Me4BrAIn API Store - Batch Ingestion")
    print("=" * 50)

    # Filter by priority if needed
    apis_to_ingest = sorted(PRIORITY_APIS, key=lambda a: a.priority)

    print(f"\n📋 APIs to ingest: {len(apis_to_ingest)}")
    for api in apis_to_ingest:
        exists = "✓" if api.path.exists() else "✗"
        print(f"  [{exists}] {api.name} ({api.category}) - Priority {api.priority}")

    # Create ingester
    ingester = create_openapi_ingester()

    # Track results
    total_tools = 0
    successful = 0
    failed = 0

    for api in apis_to_ingest:
        tool_ids = await ingest_api(ingester, api)
        if tool_ids:
            total_tools += len(tool_ids)
            successful += 1
        else:
            failed += 1

    print("\n" + "=" * 50)
    print(f"📊 Results:")
    print(f"  ✅ Successful: {successful}")
    print(f"  ❌ Failed: {failed}")
    print(f"  🔧 Total Tools Created: {total_tools}")


if __name__ == "__main__":
    asyncio.run(main())
