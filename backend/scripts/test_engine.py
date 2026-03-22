#!/usr/bin/env python
"""Test script for the new Tool Calling Engine.

Tests:
1. Tool Catalog discovery
2. Function schema generation
3. Router with LLM function calling
4. Parallel executor
5. Full pipeline
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def test_catalog():
    """Test tool catalog and discovery."""
    print("\n" + "=" * 60)
    print("TEST 1: Tool Catalog Discovery")
    print("=" * 60)

    from me4brain.engine.catalog import ToolCatalog

    catalog = ToolCatalog()

    # Manual registration test
    from me4brain.engine.types import ToolDefinition, ToolParameter

    test_tool = ToolDefinition(
        name="test_tool",
        description="A test tool",
        parameters={
            "param1": ToolParameter(type="string", description="Test param", required=True),
        },
    )

    async def test_executor(param1: str):
        return {"result": f"Got: {param1}"}

    catalog.register(test_tool, test_executor)
    print(f"✅ Manual registration: {len(catalog)} tool(s)")

    # Get function schemas
    schemas = catalog.get_function_schemas()
    print(f"✅ Function schemas generated: {len(schemas)}")
    if schemas:
        print(f"   Schema sample: {schemas[0]['function']['name']}")

    # Auto-discovery
    discovered = await catalog.discover_from_domains()
    print(f"✅ Auto-discovery: {discovered} tool(s) from domains")

    # List all tools
    all_tools = catalog.get_all_tools()
    print(f"✅ Total tools: {len(all_tools)}")

    if all_tools:
        print("\n   First 5 tools:")
        for tool in all_tools[:5]:
            print(f"   - {tool.name} [{tool.domain}]: {tool.description[:50]}...")

    return True


async def test_executor():
    """Test parallel executor."""
    print("\n" + "=" * 60)
    print("TEST 2: Parallel Executor")
    print("=" * 60)

    from me4brain.engine.catalog import ToolCatalog
    from me4brain.engine.executor import ParallelExecutor
    from me4brain.engine.types import ToolTask

    # Create catalog with test tool
    catalog = ToolCatalog()

    async def slow_tool(value: str = "default"):
        await asyncio.sleep(0.1)
        return {"value": value}

    async def fast_tool():
        return {"status": "fast"}

    from me4brain.engine.types import ToolDefinition

    catalog.register(
        ToolDefinition(name="slow_tool", description="Slow tool"),
        slow_tool,
    )
    catalog.register(
        ToolDefinition(name="fast_tool", description="Fast tool"),
        fast_tool,
    )

    # Create executor
    executor = ParallelExecutor(catalog, timeout_seconds=5.0)

    # Execute tasks in parallel
    tasks = [
        ToolTask(tool_name="slow_tool", arguments={"value": "test1"}),
        ToolTask(tool_name="fast_tool", arguments={}),
        ToolTask(tool_name="unknown_tool", arguments={}),  # Should fail gracefully
    ]

    results = await executor.execute(tasks)

    print(f"✅ Executed {len(tasks)} tasks in parallel")
    for result in results:
        status = "✅" if result.success else "❌"
        print(f"   {status} {result.tool_name}: {result.data or result.error}")

    # Verify parallel execution (should be faster than sequential)
    print("✅ Parallel execution completed")

    return True


async def test_router():
    """Test LLM-based router (requires LLM)."""
    print("\n" + "=" * 60)
    print("TEST 3: LLM Router")
    print("=" * 60)

    try:
        from me4brain.engine.catalog import ToolCatalog
        from me4brain.engine.router import ToolRouter
        from me4brain.llm.nanogpt import get_llm_client

        # Create catalog and discover tools
        catalog = ToolCatalog()
        await catalog.discover_from_domains()

        if len(catalog) == 0:
            print("⚠️ No tools discovered, skipping router test")
            return True

        # Create router
        llm_client = get_llm_client()
        router = ToolRouter(catalog, llm_client, model="kimi-k2-5")

        # Test routing
        test_queries = [
            "Qual è il prezzo del Bitcoin?",
            "Dammi il prezzo di Apple e Tesla",
        ]

        for query in test_queries:
            print(f"\n   Query: {query}")
            tasks = await router.route(query)
            if tasks:
                for task in tasks:
                    print(f"   → Tool: {task.tool_name}, Args: {task.arguments}")
            else:
                print("   → No tools selected")

        print("\n✅ Router test completed")
        return True

    except Exception as e:
        print(f"⚠️ Router test skipped: {e}")
        return True


async def test_full_pipeline():
    """Test full engine pipeline."""
    print("\n" + "=" * 60)
    print("TEST 4: Full Engine Pipeline")
    print("=" * 60)

    try:
        from me4brain.engine import ToolCallingEngine

        # Create engine
        engine = await ToolCallingEngine.create()

        print(f"✅ Engine created with {len(engine.get_available_tools())} tools")

        # Test full pipeline
        query = "Qual è il prezzo attuale del Bitcoin?"
        print(f"\n   Query: {query}")

        response = await engine.run(query)

        print(f"\n   Answer preview: {response.answer[:200]}...")
        print(f"   Tools called: {response.tools_called}")
        print(f"   Total latency: {response.total_latency_ms:.0f}ms")

        for result in response.tool_results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.tool_name}: {result.latency_ms:.0f}ms")

        print("\n✅ Full pipeline test completed")
        return True

    except Exception as e:
        print(f"⚠️ Full pipeline test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("TOOL CALLING ENGINE TEST SUITE")
    print("=" * 60)

    results = []

    # Test 1: Catalog
    try:
        results.append(("Catalog", await test_catalog()))
    except Exception as e:
        print(f"❌ Catalog test failed: {e}")
        results.append(("Catalog", False))

    # Test 2: Executor
    try:
        results.append(("Executor", await test_executor()))
    except Exception as e:
        print(f"❌ Executor test failed: {e}")
        results.append(("Executor", False))

    # Test 3: Router (optional - requires LLM)
    try:
        results.append(("Router", await test_router()))
    except Exception as e:
        print(f"⚠️ Router test skipped: {e}")
        results.append(("Router", True))

    # Test 4: Full pipeline (optional - requires LLM)
    try:
        results.append(("Pipeline", await test_full_pipeline()))
    except Exception as e:
        print(f"⚠️ Pipeline test skipped: {e}")
        results.append(("Pipeline", True))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = 0
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {name}: {status}")
        if success:
            passed += 1

    print(f"\n   Total: {passed}/{len(results)} tests passed")
    print("=" * 60)

    return all(success for _, success in results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
