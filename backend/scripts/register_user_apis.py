#!/usr/bin/env python3
"""Register User API wrappers in the API Store.

Registers FRED, PubMed, BallDontLie, and Odds API tools.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from me4brain.memory.procedural import get_procedural_memory, Tool
from me4brain.integrations.user_apis import USER_API_TOOLS


async def register_user_api_tools():
    """Register all User API tools in the API Store."""
    print("🔧 Registering User API Tools (FRED, PubMed, NBA, Odds)")
    print("=" * 50)

    proc_memory = get_procedural_memory()
    await proc_memory.initialize()

    tenant_id = "me4brain_core"
    tools_created = []

    for tool_def in USER_API_TOOLS:
        tool = Tool(
            id=str(uuid4()),
            name=tool_def["name"],
            description=tool_def["description"],
            tenant_id=tenant_id,
            endpoint=f"internal://{tool_def['service']}/{tool_def['method']}",
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

            # Register intent with high weight for user's own APIs
            intent_text = f"User API: {tool_def['description']}"
            proc_memory.register_intent(
                tenant_id=tenant_id,
                intent=intent_text,
                tool_ids=[tool_id],
                initial_weight=0.8,  # High priority for user's custom APIs
            )

            print(f"  ✅ {tool_def['name']}")

        except Exception as e:
            print(f"  ❌ {tool_def['name']}: {e}")

    print("\n" + "=" * 50)
    print(f"📊 Registered {len(tools_created)} User API tools")
    return tools_created


if __name__ == "__main__":
    asyncio.run(register_user_api_tools())
