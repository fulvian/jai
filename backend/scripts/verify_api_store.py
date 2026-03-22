#!/usr/bin/env python3
"""API Store Verification Script.

Verifies the Dynamic API Store by:
1. Counting registered tools
2. Testing semantic search for tools
3. Validating Skill Graph integrity
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from me4brain.memory.procedural import get_procedural_memory
from me4brain.embeddings import get_embedding_service


async def main():
    """Verify API Store state."""
    print("🔍 API Store Verification")
    print("=" * 50)

    # Get services
    proc_memory = get_procedural_memory()
    embedding_svc = get_embedding_service()

    # Initialize if needed
    await proc_memory.initialize()

    tenant_id = "me4brain_core"

    # Test 1: Count tools in Skill Graph
    print("\n📊 Tool Count in Skill Graph:")
    semantic = proc_memory.get_semantic()
    kuzu = semantic.get_connection()

    try:
        result = kuzu.execute(
            "MATCH (t:Entity) WHERE t.tenant_id = $tenant AND t.type = 'Tool' RETURN count(t) as cnt",
            {"tenant": tenant_id},
        )
        tool_count = list(result)[0][0] if result else 0
        print(f"  ✅ Total Tools: {tool_count}")
    except Exception as e:
        print(f"  ❌ Error counting tools: {e}")
        tool_count = 0

    # Test 2: Count intents
    print("\n📋 Intent Count:")
    try:
        result = kuzu.execute(
            "MATCH (i:Entity) WHERE i.tenant_id = $tenant AND i.type = 'Intent' RETURN count(i) as cnt",
            {"tenant": tenant_id},
        )
        intent_count = list(result)[0][0] if result else 0
        print(f"  ✅ Total Intents: {intent_count}")
    except Exception as e:
        print(f"  ❌ Error counting intents: {e}")
        intent_count = 0

    # Test 3: Semantic search for a tool
    print("\n🔎 Semantic Search Test:")
    test_queries = [
        "send an email",
        "get weather forecast",
        "create a task in project management",
        "search for images",
        "test HTTP requests",
    ]

    for query in test_queries:
        try:
            embedding = embedding_svc.embed_query(query)
            tools = await proc_memory.find_tools_for_intent(
                tenant_id=tenant_id,
                intent_embedding=embedding,
                top_k=3,
            )
            if tools:
                tool_names = [t[0].name for t in tools[:3]]
                print(f"  ✅ '{query}' → {tool_names}")
            else:
                print(f"  ⚠️  '{query}' → No tools found")
        except Exception as e:
            print(f"  ❌ Error for '{query}': {e}")

    # Summary
    print("\n" + "=" * 50)
    print("📊 Summary:")
    print(f"  • Tools Registered: {tool_count}")
    print(f"  • Intents Registered: {intent_count}")
    print(f"  • API Store Status: {'✅ OPERATIONAL' if tool_count > 0 else '❌ EMPTY'}")


if __name__ == "__main__":
    asyncio.run(main())
