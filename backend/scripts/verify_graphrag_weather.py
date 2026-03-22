import asyncio
import os
import sys
from unittest.mock import MagicMock

# Aggiungi src al path
sys.path.append(os.path.abspath("src"))

from me4brain.engine.iterative_executor import IterativeExecutor
from me4brain.engine.hybrid_router.types import SubQuery, RetrievedTool


async def verify():
    print("🔍 Verificando Hand-Crafted GraphRAG (SOTA 2026)...")

    # Setup Mock
    llm = MagicMock()
    retriever = MagicMock()
    executor = MagicMock()

    it_exec = IterativeExecutor(llm, retriever, executor)

    # Mocking RetrievedTool for weather
    weather_tool = RetrievedTool(
        name="openmeteo_weather",
        description="Get weather",
        schema={"type": "function", "function": {"name": "openmeteo_weather", "parameters": {}}},
        score=1.0,
    )

    sq = SubQuery(text="Che tempo fa a Roma?", domain="weather_geo")

    print("\n[Layer 1] Test Retrieval Prompt da Neo4j...")
    hints = await it_exec._get_graph_prompt_hints(
        domain=sq.domain, tool_names=["openmeteo_weather"]
    )

    if "WEATHER:" in hints or "DOMAIN [WEATHER_GEO]" in hints:
        print("✅ Successo: Prompt del dominio o del tool recuperato!")
        print("-" * 30)
        print(hints[:300] + "...")
        print("-" * 30)
    else:
        print("❌ Fallimento: Prompt non trovato nel grafo.")

    print("\n[Layer 2] Test System Prompt Construction...")
    full_prompt = await it_exec._build_step_prompt(
        step_id=1, total_tools=1, current_datetime="2026-02-22 18:00", graph_hints=hints
    )

    if "STRICT TOOL GUIDELINES" in full_prompt:
        print("✅ Successo: Sezione STRICT TOOL GUIDELINES iniettata correttamente.")
    else:
        print("❌ Fallimento: Sezione GUIDELINES mancante nel system prompt.")


if __name__ == "__main__":
    asyncio.run(verify())
