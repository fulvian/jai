import asyncio
import os
import sys
from unittest.mock import MagicMock

from dotenv import load_dotenv

# Aggiungi src al path per importare me4brain
sys.path.append(os.path.abspath("src"))

# Carica .env locale
load_dotenv(".env")

from me4brain.domains.web_search.tools.search_api import smart_search


async def test_routing():
    print("🚀 Test Routing Smart Search (3-Tier)...")

    # Mocking logger and APIs to avoid actual network calls during logic validation
    # (Or just look at the logs if we run it for real)

    queries = [
        ("Cosa è successo oggi in Ucraina?", "Brave", "News"),
        ("site:github.com me4brain", "Brave", "Site/Broad"),
        (
            "Spiegami la differenza tra RAG e Fine-tuning con un'analisi dettagliata",
            "Tavily",
            "Complex",
        ),
        ("Perché il cielo è blu?", "Tavily", "Why/Complex"),
        ("Capitale della Francia", "DuckDuckGo", "Fact/Quick"),
    ]

    for q, expected, reason in queries:
        print(f"\nQuery: '{q}'")
        print(f"Expected Tier: {expected} ({reason})")
        # Nota: Eseguiamo la chiamata reale per vedere il logging del routing
        try:
            # Forziamo il caricamento delle env per sicurezza
            res = await smart_search(q)
            print(f"✅ Eseguito con successo (Provider: {res.get('provider', 'N/D')})")
        except Exception as e:
            print(f"❌ Errore durante l'esecuzione: {e}")


if __name__ == "__main__":
    asyncio.run(test_routing())
