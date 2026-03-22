#!/usr/bin/env python3
"""Script di verifica allineamento tra tool_hierarchy.yaml e tool definitions reali.

Usage:
    python scripts/verify_tool_hierarchy.py

Questo script confronta:
1. I tool definiti in config/tool_hierarchy.yaml
2. I tool caricati dinamicamente dai moduli dominio

Output:
- Tool in codice ma non in YAML
- Tool in YAML ma non in codice
- Disallineamenti nei nomi
"""

import asyncio
import sys
from pathlib import Path


async def verify_hierarchy():
    """Verifica allineamento tool hierarchy."""
    print("=" * 60)
    print("🔍 VERIFICA TOOL HIERARCHY")
    print("=" * 60)

    # 1. Carica tool hierarchy da YAML
    import yaml

    hierarchy_path = Path(__file__).parent.parent / "config" / "tool_hierarchy.yaml"

    if not hierarchy_path.exists():
        print(f"❌ File non trovato: {hierarchy_path}")
        return 1

    with open(hierarchy_path) as f:
        hierarchy = yaml.safe_load(f) or {}

    # Estrai tool names dal YAML
    yaml_tools = set()
    yaml_tool_to_path = {}  # tool -> "domain > category > skill"

    for domain, categories in hierarchy.items():
        if not isinstance(categories, dict):
            continue
        for category, skills in categories.items():
            if not isinstance(skills, dict):
                continue
            for skill, tools in skills.items():
                if not isinstance(tools, list):
                    continue
                for tool in tools:
                    yaml_tools.add(tool)
                    yaml_tool_to_path[tool] = f"{domain} > {category} > {skill}"

    print(f"\n📋 Tool definiti in YAML: {len(yaml_tools)}")

    # 2. Carica tool definitions reali
    print("\n📦 Caricamento tool definitions dai domini...")

    try:
        from me4brain.domains import (
            entertainment,
            finance_crypto,
            food,
            geo_weather,
            google_workspace,
            jobs,
            knowledge_media,
            medical,
            science_research,
            sports_booking,
            sports_nba,
            tech_coding,
            travel,
            utility,
            web_search,
        )

        domain_modules = [
            ("entertainment", "me4brain.domains.entertainment.tools.entertainment_api"),
            ("finance_crypto", "me4brain.domains.finance_crypto.tools.finance_api"),
            ("food", "me4brain.domains.food.tools.food_api"),
            ("geo_weather", "me4brain.domains.geo_weather.tools.geo_api"),
            ("google_workspace", "me4brain.domains.google_workspace.tools.google_api"),
            ("jobs", "me4brain.domains.jobs.tools.jobs_api"),
            ("knowledge_media", "me4brain.domains.knowledge_media.tools.knowledge_api"),
            ("medical", "me4brain.domains.medical.tools.medical_api"),
            ("science_research", "me4brain.domains.science_research.tools.science_api"),
            ("sports_booking", "me4brain.domains.sports_booking.tools.playtomic_api"),
            ("sports_nba", "me4brain.domains.sports_nba.tools.nba_api"),
            ("tech_coding", "me4brain.domains.tech_coding.tools.tech_api"),
            ("travel", "me4brain.domains.travel.tools.travel_api"),
            ("utility", "me4brain.domains.utility.tools"),
            ("web_search", "me4brain.domains.web_search.tools.search_api"),
        ]

        code_tools = set()
        for domain_name, module_path in domain_modules:
            try:
                module = __import__(module_path, fromlist=["get_tool_definitions"])
                tools = module.get_tool_definitions()
                for tool in tools:
                    code_tools.add(tool.name)
                print(f"   ✅ {domain_name}: {len(tools)} tools")
            except Exception as e:
                print(f"   ❌ {domain_name}: {e}")

    except Exception as e:
        print(f"❌ Errore caricamento domini: {e}")
        return 1

    print(f"\n📋 Tool definiti nel codice: {len(code_tools)}")

    # 3. Analizza discrepanze
    print("\n" + "=" * 60)
    print("📊 RISULTATI VERIFICA")
    print("=" * 60)

    # Tool in codice ma non in YAML
    in_code_not_yaml = code_tools - yaml_tools
    if in_code_not_yaml:
        print(f"\n⚠️ Tool nel codice ma NON in YAML ({len(in_code_not_yaml)}):")
        for tool in sorted(in_code_not_yaml)[:20]:
            print(f"   - {tool}")
        if len(in_code_not_yaml) > 20:
            print(f"   ... e altri {len(in_code_not_yaml) - 20}")
    else:
        print("\n✅ Tutti i tool del codice sono presenti nel YAML")

    # Tool in YAML ma non in codice
    in_yaml_not_code = yaml_tools - code_tools
    if in_yaml_not_code:
        print(f"\n⚠️ Tool nel YAML ma NON nel codice ({len(in_yaml_not_code)}):")
        for tool in sorted(in_yaml_not_code):
            path = yaml_tool_to_path.get(tool, "unknown")
            print(f"   - {tool} ({path})")
    else:
        print("\n✅ Tutti i tool del YAML sono presenti nel codice")

    # Tool con nomi simili (probabili errori di naming)
    print("\n🔍 Possibili errori di naming:")
    similar_issues = []

    # Trova tool che potrebbero essere la stessa cosa con naming diverso
    for code_tool in code_tools:
        for yaml_tool in yaml_tools:
            # Stesso tool con prefisso diverso
            if code_tool != yaml_tool:
                # google_gmail_search vs gmail_search
                if code_tool.replace("google_", "") == yaml_tool:
                    similar_issues.append((code_tool, yaml_tool, "prefix"))
                # drive_search vs google_drive_search
                elif yaml_tool.replace("google_", "") == code_tool:
                    similar_issues.append((code_tool, yaml_tool, "prefix"))

    if similar_issues:
        for code, yaml, issue in similar_issues:
            print(f"   - {code} ≈ {yaml} ({issue})")
    else:
        print("   Nessun problema di naming rilevato")

    # 4. Genera correzioni suggerite
    print("\n" + "=" * 60)
    print("📝 CORREZIONI SUGGERITE")
    print("=" * 60)

    if in_code_not_yaml:
        print("\nAggiungi al file tool_hierarchy.yaml nella sezione appropriata:")
        # Suggerisci dove aggiungere i tool mancanti
        by_prefix = {}
        for tool in sorted(in_code_not_yaml):
            # Determina il dominio dal nome
            if (
                "gmail" in tool.lower()
                or "drive" in tool.lower()
                or "calendar" in tool.lower()
                or "docs" in tool.lower()
                or "sheets" in tool.lower()
                or "meet" in tool.lower()
            ):
                domain = "google_workspace"
            elif (
                "crypto" in tool.lower()
                or "binance" in tool.lower()
                or "coingecko" in tool.lower()
                or "stock" in tool.lower()
                or "yahoo" in tool.lower()
                or "finnhub" in tool.lower()
            ):
                domain = "finance_crypto"
            elif "nba" in tool.lower() or "sports" in tool.lower() or "betting" in tool.lower():
                domain = "sports_nba"
            elif "arxiv" in tool.lower() or "pubmed" in tool.lower() or "semantic" in tool.lower():
                domain = "science_research"
            elif "weather" in tool.lower() or "meteo" in tool.lower():
                domain = "geo_weather"
            else:
                domain = "utility"

            if domain not in by_prefix:
                by_prefix[domain] = []
            by_prefix[domain].append(tool)

        for domain, tools in sorted(by_prefix.items()):
            print(f"\n{domain}:")
            for tool in tools:
                print(f"  - {tool}")

    print("\n✅ Verifica completata!")
    return 0


async def main():
    return await verify_hierarchy()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
