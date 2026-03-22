#!/usr/bin/env python3
"""Minimal debug script - test domain classification only."""

import asyncio
import sys
import json
from pathlib import Path


async def test_domain_classification():
    """Test domain classifier directly without full router."""

    from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
    from me4brain.engine.hybrid_router.types import HybridRouterConfig
    from me4brain.llm.nanogpt import get_llm_client

    query = "Analizza le partite NBA stasera, identifica i migliori pronostici ed elabora un sistema di scommesse vincente"

    print("\n" + "=" * 80)
    print("DOMAIN CLASSIFIER DEBUG - NBA BETTING QUERY")
    print("=" * 80)
    print(f"Query: {query}\n")

    try:
        # Initialize LLM
        print("[1/2] Initializing LLM client...")
        llm_client = get_llm_client()
        print("✓ LLM initialized\n")

        # Initialize classifier
        print("[2/2] Initializing DomainClassifier...")
        config = HybridRouterConfig()
        available_domains = ["sports_nba", "web_search", "finance_crypto", "geo_weather"]

        classifier = DomainClassifier(
            llm_client=llm_client,
            available_domains=available_domains,
            config=config,
        )
        print("✓ Classifier initialized\n")

        # Run classification
        print("=" * 80)
        print("CLASSIFYING QUERY")
        print("=" * 80 + "\n")

        import time

        start = time.time()

        try:
            classification, used_fallback = await asyncio.wait_for(
                classifier.classify_with_fallback(query=query), timeout=30.0
            )

            elapsed = time.time() - start

            print(f"\n✓ Classification completed in {elapsed:.2f}s")
            print(f"\nResult:")
            print(f"  Domains: {classification.domain_names}")
            print(f"  Confidence: {classification.confidence}")
            print(f"  Used fallback: {used_fallback}")
            print(f"  Summary: {classification.query_summary}")

            # Write result
            result = {
                "query": query,
                "domains": classification.domain_names,
                "confidence": classification.confidence,
                "used_fallback": used_fallback,
                "summary": classification.query_summary,
                "status": "success",
                "elapsed_ms": int(elapsed * 1000),
            }

            with open("/tmp/classifier_result.json", "w") as f:
                json.dump(result, f, indent=2)

            print("\n✓ Result saved to /tmp/classifier_result.json")

            # Verify result
            if "sports_nba" in classification.domain_names:
                print("\n✅ CORRECT: Query correctly classified as sports_nba")
                return True
            else:
                print(f"\n❌ WRONG: Expected sports_nba, got {classification.domain_names}")
                return False

        except asyncio.TimeoutError:
            print("\n❌ TIMEOUT: Classification exceeded 30 seconds")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_domain_classification())
    sys.exit(0 if result else 1)
