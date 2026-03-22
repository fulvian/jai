#!/usr/bin/env python3
"""Test E2E con tracing dati per identificare dove si perdono."""

import asyncio
import json


async def test():
    from me4brain.llm.nanogpt import get_llm_client
    from me4brain.llm.config import get_llm_config
    from me4brain.core.cognitive_pipeline import (
        analyze_query,
        execute_semantic_tool_loop,
        synthesize_response,
    )
    from me4brain.embeddings import get_embedding_service
    from me4brain.retrieval.tool_executor import ToolExecutor

    llm_client = get_llm_client()
    config = get_llm_config()
    embedding_service = get_embedding_service()
    executor = ToolExecutor()

    query = "Dammi il prezzo di Bitcoin ed Ethereum"
    tenant_id = "debug"
    user_id = "debug-test"

    print("=" * 60)
    print("STEP 1: analyze_query")
    print("=" * 60)
    analysis = await analyze_query(query, llm_client, config)
    print(f"Domains: {analysis.get('domains_required')}")
    print(f"Entities: {json.dumps(analysis.get('entities', []), indent=2)}")

    print("\n" + "=" * 60)
    print("STEP 2: execute_semantic_tool_loop")
    print("=" * 60)
    collected_data = await execute_semantic_tool_loop(
        tenant_id=tenant_id,
        user_id=user_id,
        user_query=query,
        executor=executor,
        embedding_service=embedding_service,
        llm_client=llm_client,
        config=config,
        analysis=analysis,
    )

    print(f"\nCollected data count: {len(collected_data)}")
    for i, item in enumerate(collected_data):
        print(f"\n--- Item {i + 1} ---")
        print(f"  success: {item.get('success')}")
        print(f"  tool_name: {item.get('tool_name')}")
        print(f"  _domain: {item.get('_domain')}")
        data = item.get("data", {})
        print(f"  data type: {type(data)}")
        print(f"  data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        if isinstance(data, dict) and "prices" in data:
            print(f"  PRICES FOUND: {list(data['prices'].keys())}")
        elif isinstance(data, dict) and data:
            print(f"  data preview: {str(data)[:200]}")
        else:
            print(f"  DATA EMPTY OR MISSING!")

    print("\n" + "=" * 60)
    print("STEP 3: synthesize_response (preview)")
    print("=" * 60)
    response = await synthesize_response(
        query=query,
        analysis=analysis,
        collected_data=collected_data,
        memory_context="",
        llm_client=llm_client,
        config=config,
    )
    print(f"Response length: {len(response)} chars")
    print(f"Response preview: {response[:500]}")


if __name__ == "__main__":
    asyncio.run(test())
