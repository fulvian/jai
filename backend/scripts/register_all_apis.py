#!/usr/bin/env python3
"""Register ALL API wrappers in the API Store.

Registers:
- Public APIs (30 tools) - No auth required
- Premium APIs (15 tools) - API key required
- Total: 45+ additional tools
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from me4brain.memory.procedural import get_procedural_memory, Tool
from me4brain.integrations.public_apis import PUBLIC_API_TOOLS
from me4brain.integrations.premium_apis import PREMIUM_API_TOOLS


async def register_all_apis():
    """Register all API tools in the API Store."""
    print("🚀 Massive API Registration")
    print("=" * 60)

    proc_memory = get_procedural_memory()
    await proc_memory.initialize()

    tenant_id = "me4brain_core"
    tools_created = []

    all_tools = [
        ("🆓 Public APIs (No Auth)", PUBLIC_API_TOOLS),
        ("🔑 Premium APIs (Key Required)", PREMIUM_API_TOOLS),
    ]

    for category_name, tool_list in all_tools:
        print(f"\n{category_name}")
        print("-" * 40)

        for tool_def in tool_list:
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

                # Register intent
                intent_text = tool_def["description"]
                proc_memory.register_intent(
                    tenant_id=tenant_id,
                    intent=intent_text,
                    tool_ids=[tool_id],
                    initial_weight=0.6,
                )

                print(f"  ✅ {tool_def['name']}")

            except Exception as e:
                print(f"  ❌ {tool_def['name']}: {e}")

    print("\n" + "=" * 60)
    print(f"📊 Registered {len(tools_created)} new API tools")

    # Summary
    print("\n📋 Summary:")
    print(f"  • Public APIs: {len(PUBLIC_API_TOOLS)}")
    print(f"  • Premium APIs: {len(PREMIUM_API_TOOLS)}")
    print(f"  • Total New: {len(tools_created)}")

    return tools_created


if __name__ == "__main__":
    asyncio.run(register_all_apis())
