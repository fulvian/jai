#!/usr/bin/env python3
"""Register Google Workspace tools in the API Store.

This script:
1. Creates Tool entities for each Google Workspace operation
2. Registers them in the Skill Graph (KuzuDB)
3. Creates Intent nodes for semantic routing
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from me4brain.memory.procedural import get_procedural_memory, Tool
from me4brain.integrations.google_workspace import GOOGLE_WORKSPACE_TOOLS
from me4brain.embeddings import get_embedding_service


async def register_google_workspace_tools():
    """Register all Google Workspace tools in the API Store."""
    print("🔧 Registering Google Workspace Tools")
    print("=" * 50)

    proc_memory = get_procedural_memory()
    await proc_memory.initialize()

    tenant_id = "me4brain_core"
    tools_created = []

    for tool_def in GOOGLE_WORKSPACE_TOOLS:
        tool = Tool(
            id=str(uuid4()),
            name=tool_def["name"],
            description=tool_def["description"],
            tenant_id=tenant_id,
            endpoint=f"internal://google_workspace/{tool_def['method']}",
            method="INTERNAL",
            api_schema=tool_def.get("parameters", {}),
            status="ACTIVE",
            version="1.0",
            success_rate=0.5,
            avg_latency_ms=0.0,
            total_calls=0,
        )

        try:
            tool_id = proc_memory.register_tool(tool)
            tools_created.append(tool_id)

            # Register intent
            intent_text = f"Google Workspace: {tool_def['description']}"
            proc_memory.register_intent(
                tenant_id=tenant_id,
                intent=intent_text,
                tool_ids=[tool_id],
                initial_weight=0.7,  # Higher weight for first-party integrations
            )

            print(f"  ✅ {tool_def['name']}")

        except Exception as e:
            print(f"  ❌ {tool_def['name']}: {e}")

    print("\n" + "=" * 50)
    print(f"📊 Registered {len(tools_created)} Google Workspace tools")
    return tools_created


if __name__ == "__main__":
    asyncio.run(register_google_workspace_tools())
