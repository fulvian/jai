#!/usr/bin/env python3
"""Test per vedere risposta COMPLETA."""

import asyncio


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

    analysis = await analyze_query(query, llm_client, config)

    collected_data = await execute_semantic_tool_loop(
        tenant_id="test",
        user_id="test",
        user_query=query,
        executor=executor,
        embedding_service=embedding_service,
        llm_client=llm_client,
        config=config,
        analysis=analysis,
    )

    response = await synthesize_response(
        query=query,
        analysis=analysis,
        collected_data=collected_data,
        memory_context="",
        llm_client=llm_client,
        config=config,
    )

    print("=" * 60)
    print("RISPOSTA COMPLETA:")
    print("=" * 60)
    print(response)


if __name__ == "__main__":
    asyncio.run(test())
