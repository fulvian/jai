#!/usr/bin/env python3
"""Test query decomposer."""

import asyncio
import json


async def test_decomposer():
    """Test query decomposition for betting query."""

    from me4brain.engine.hybrid_router.query_decomposer import QueryDecomposer
    from me4brain.engine.hybrid_router.types import (
        HybridRouterConfig,
        DomainClassification,
        DomainComplexity,
    )
    from me4brain.llm.nanogpt import get_llm_client

    query = "Analizza le partite NBA stasera, identifica i migliori pronostici ed elabora un sistema di scommesse vincente"

    print("\n" + "=" * 80)
    print("QUERY DECOMPOSER DEBUG - NBA BETTING QUERY")
    print("=" * 80)
    print(f"Query: {query}\n")

    try:
        # Initialize
        print("[1/2] Initializing LLM client...")
        llm_client = get_llm_client()
        print("✓ LLM initialized\n")

        print("[2/2] Initializing QueryDecomposer...")
        config = HybridRouterConfig(use_query_decomposition=True)
        available_domains = ["sports_nba", "web_search"]

        decomposer = QueryDecomposer(
            llm_client=llm_client,
            available_domains=available_domains,
            config=config,
        )
        print("✓ Decomposer initialized\n")

        # Create classification
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="high")],
            confidence=0.9,
            query_summary="NBA betting analysis query",
        )

        print("=" * 80)
        print("DECOMPOSING QUERY")
        print("=" * 80 + "\n")

        import time

        start = time.time()

        try:
            sub_queries = await asyncio.wait_for(
                decomposer.decompose(query=query, classification=classification), timeout=30.0
            )

            elapsed = time.time() - start

            print(f"\n✓ Decomposition completed in {elapsed:.2f}s")
            print(f"\nGenerated {len(sub_queries)} sub-queries:")

            for i, sq in enumerate(sub_queries, 1):
                print(f"\n  [{i}] {sq.text}")
                print(f"      Domain: {sq.domain}")
                print(f"      Intent: {sq.intent}")

            result = {
                "query": query,
                "sub_query_count": len(sub_queries),
                "sub_queries": [
                    {
                        "text": sq.text,
                        "domain": sq.domain,
                        "intent": sq.intent,
                    }
                    for sq in sub_queries
                ],
                "status": "success",
                "elapsed_ms": int(elapsed * 1000),
            }

            with open("/tmp/decomposer_result.json", "w") as f:
                json.dump(result, f, indent=2)

            print("\n✓ Result saved to /tmp/decomposer_result.json")

            if len(sub_queries) == 0:
                print("\n❌ WARNING: No sub-queries generated!")
                return False
            else:
                print(f"\n✅ Generated {len(sub_queries)} sub-queries")
                return True

        except asyncio.TimeoutError:
            print("\n❌ TIMEOUT: Decomposition exceeded 30 seconds")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys

    result = asyncio.run(test_decomposer())
    sys.exit(0 if result else 1)
