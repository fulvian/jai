import asyncio
import os
import sys

# Aggiungi src al path
sys.path.append(os.path.join(os.getcwd(), "src"))

from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
from me4brain.engine.hybrid_router.types import HybridRouterConfig
from me4brain.llm.provider_factory import get_reasoning_client


async def test_classification():
    # Setup
    llm = await get_reasoning_client()
    domains = [
        "communication",
        "scheduling",
        "file_management",
        "content_creation",
        "data_analysis",
        "finance_crypto",
        "geo_weather",
        "web_search",
        "travel",
        "food",
        "entertainment",
        "sports_nba",
        "sports_booking",
        "jobs",
        "medical",
        "knowledge_media",
        "utility",
    ]
    # Mock router config as core.py does (injecting the correct model)
    config = HybridRouterConfig()
    # In OllamaClient the attribute is model_name, not model
    model_path = getattr(llm, "model_name", getattr(llm, "model", "default"))
    print(f"DEBUG: Using model_path='{model_path}'")
    config.router_model = model_path  # 🎯 CRITICAL: This is what core.py does

    classifier = DomainClassifier(llm, domains, config)

    queries = [
        "che tempo fa a Caltanissetta?",
        "prezzo Bitcoin oggi",
        "cerca email di Mario",
        "crea un nuovo documento word",
        "prenota un volo per Parigi",
        "chi è il presidente degli Stati Uniti?",
    ]

    for query in queries:
        print("\n" + "=" * 50)
        print(f"Testing classification for: '{query}'")

        # Direct classify
        result = await classifier.classify(query)
        print("Classification Result:")
        print(f"  Domains: {[d.name for d in result.domains]}")
        print(f"  Confidence: {result.confidence}")

        # Classify with fallback (this highlights if keywords are working)
        result_fb, was_fb = await classifier.classify_with_fallback(query)
        print(f"Classification with Fallback (was_fb={was_fb}):")
        print(f"  Domains: {[d.name for d in result_fb.domains]}")


if __name__ == "__main__":
    asyncio.run(test_classification())
