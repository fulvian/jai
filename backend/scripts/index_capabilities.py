#!/usr/bin/env python3
"""Script di indicizzazione unificato per tools e skills.

Indicizza tutti gli strumenti (tools) e le competenze (skills) nella collection
unificata me4brain_capabilities. Questo script sostituisce:
- scripts/sync_tools_qdrant.py
- scripts/reindex_tools.py

Usage:
    python scripts/index_capabilities.py [--tools-only] [--skills-only] [--force]

Il sistema di change detection evita reindicizzazione se non necessario.
"""

import asyncio
import gc
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

# Configurazione
QDRANT_URL = "http://qdrant:6334"
QDRANT_URL_LOCAL = "http://localhost:6334"
TIMEOUT = 60
COLLECTION = "me4brain_capabilities"


def get_qdrant_client():
    """Ottiene client Qdrant."""
    import os

    # SOTA 2026: Priority to environment variable for remote deployment
    env_host = os.getenv("QDRANT_HOST")
    if env_host:
        try:
            url = f"http://{env_host}:6334"
            client = QdrantClient(url=url, timeout=TIMEOUT)
            client.get_collections()
            print(f"✅ Connesso a Qdrant (Environment): {url}")
            return client
        except Exception as e:
            print(f"⚠️ Errore connessione Qdrant via QDRANT_HOST ({env_host}): {e}")

    try:
        client = QdrantClient(url=QDRANT_URL, timeout=TIMEOUT)
        client.get_collections()
        print(f"✅ Connesso a Qdrant (Docker): {QDRANT_URL}")
        return client
    except Exception:
        try:
            client = QdrantClient(url=QDRANT_URL_LOCAL, timeout=TIMEOUT)
            client.get_collections()
            print(f"✅ Connesso a Qdrant (Local): {QDRANT_URL_LOCAL}")
            return client
        except Exception as e:
            print(f"❌ Impossibile connettersi a Qdrant: {e}")
            sys.exit(1)


def build_sota_embed_text(
    name: str,
    description: str,
    domain: str,
    cap_type: str = "tool",
    category: str = "",
    skill: str = "",
    tags: list = None,
) -> str:
    """Costruisce testo ottimizzato per embedding SOTA 2026."""
    tags_str = ", ".join(tags) if tags else ""

    # Costruisci gerarchia
    hierarchy_parts = [domain]
    if category:
        hierarchy_parts.append(category)
    if skill:
        hierarchy_parts.append(skill)
    hierarchy = " > ".join(hierarchy_parts)

    # Genera hint di disambiguazione
    not_suitable = get_not_suitable_hints(name, domain, category)

    if cap_type == "skill":
        return f"""[search_query]: {name}
Skill: {name}
Purpose: {description}
Use when user wants to: {description}
Hierarchy: {hierarchy}
Tags: {tags_str}
Domain: {domain}"""
    else:
        base = f"""[search_query]: {name}
Tool: {name}
Purpose: {description}
Use when user wants to: {description}
Hierarchy: {hierarchy}
Domain: {domain}"""
        if not_suitable:
            base += f"\nNOT suitable for: {not_suitable}"
        return base


def get_not_suitable_hints(name: str, domain: str, category: str) -> str:
    """Genera hint di disambiguazione."""
    hints = {
        "google_gmail_search": "searching files, Google Drive operations, document management",
        "google_gmail_get_message": "file content, Drive files, spreadsheets",
        "google_drive_search": "emails, email content, Gmail inbox",
        "google_drive_list_files": "email messages, Gmail, inbox",
        "google_calendar_upcoming": "video calls, meetings links, conference calls",
        "google_meet_create": "calendar events, scheduling, appointments",
        "coingecko_price": "stock prices, equity trading, NYSE/NASDAQ",
        "binance_price": "stock quotes, traditional markets, forex",
        "yahoo_finance_quote": "cryptocurrency, Bitcoin, Ethereum, altcoins",
        "finnhub_quote": "crypto prices, blockchain, DeFi",
        "google_docs_create": "spreadsheets, data tables, calculations",
    }
    return hints.get(name, "")


def load_domain_tools() -> list[dict]:
    """Carica tool definitions da tutti i moduli dominio."""
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

    all_tools = []

    for domain_name, module_path in domain_modules:
        try:
            module = __import__(module_path, fromlist=["get_tool_definitions"])
            tools = module.get_tool_definitions()

            for tool in tools:
                # Use tool's defined domain if available, otherwise fallback to folder name
                final_domain = (
                    tool.domain if hasattr(tool, "domain") and tool.domain else domain_name
                )

                # Estrai category e skill dalla gerarchia se disponibile
                category, skill = extract_category_skill(tool.name, final_domain)

                all_tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "domain": final_domain,
                        "category": category,
                        "skill": skill,
                        "type": "tool",
                        "subtype": "static",
                        "schema": tool.to_dict() if hasattr(tool, "to_dict") else {},
                    }
                )

            print(f"   ✅ {domain_name}: {len(tools)} tools")
        except Exception as e:
            print(f"   ❌ {domain_name}: {e}")

    return all_tools


def extract_category_skill(tool_name: str, default_domain: str) -> tuple[str, str]:
    """Estrae category e skill dal nome del tool usando pattern comuni."""
    # Pattern comuni per categorizzare
    name_lower = tool_name.lower()

    # Google Workspace
    if "gmail" in name_lower:
        if "search" in name_lower:
            return "gmail", "search"
        elif "send" in name_lower:
            return "gmail", "send"
        elif "get" in name_lower:
            return "gmail", "get"
    elif "drive" in name_lower:
        if "search" in name_lower:
            return "drive", "search"
        elif "list" in name_lower:
            return "drive", "list"
    elif "calendar" in name_lower:
        if "search" in name_lower:
            return "calendar", "search"
        elif "create" in name_lower:
            return "calendar", "manage"
    elif "docs" in name_lower:
        return "docs", "manage"
    elif "sheets" in name_lower:
        return "sheets", "read"
    elif "meet" in name_lower:
        return "meet", "manage"

    # Finance/Crypto
    if "crypto" in name_lower or "binance" in name_lower or "coingecko" in name_lower:
        if "price" in name_lower:
            return "crypto", "price"
        elif "history" in name_lower or "klines" in name_lower:
            return "crypto", "history"
    elif "stock" in name_lower or "yahoo" in name_lower or "finnhub" in name_lower:
        if "quote" in name_lower:
            return "stocks", "quote"
        elif "history" in name_lower:
            return "stocks", "history"
    elif "fred" in name_lower:
        return "macro", "fred"

    # Sports
    if "nba" in name_lower or "sports" in name_lower:
        if "odds" in name_lower or "betting" in name_lower:
            return "sports", "betting"
        elif "game" in name_lower or "schedule" in name_lower:
            return "sports", "schedule"

    # Travel
    if "flight" in name_lower or "amadeus" in name_lower:
        return "flights", "search"
    elif "hotel" in name_lower:
        return "hotels", "search"

    # Web Search
    if "search" in name_lower:
        return "general", "search"

    # Utility
    if "browser" in name_lower:
        return "browser", "navigate"
    elif "schedule" in name_lower or "agent" in name_lower:
        return "automation", "schedule"

    return "", ""


async def load_skills() -> list[dict]:
    """Carica skills da file system."""
    from me4brain.skills import SkillLoader, SkillRegistry

    loader = SkillLoader()
    registry = SkillRegistry(loader)
    await registry.initialize()

    skills = []

    for skill in registry.skills:
        # Determina dominio dai tag
        domain = determine_skill_domain(skill.metadata.tags)

        skills.append(
            {
                "name": skill.name,
                "description": skill.description,
                "domain": domain,
                "category": "",
                "skill": "",
                "type": "skill",
                "subtype": "crystallized"
                if skill.metadata.source.value == "bundled"
                else "learned",
                "skill_id": skill.id,
                "tags": skill.metadata.tags,
                "instructions": skill.instructions[:500] if skill.instructions else "",
            }
        )

    bundled = sum(1 for s in skills if s["subtype"] == "crystallized")
    learned = sum(1 for s in skills if s["subtype"] == "learned")
    print(f"   ✅ Skills: {bundled} bundled, {learned} learned")

    return skills


def determine_skill_domain(tags: list[str]) -> str:
    """Mappa tag a domini Me4BrAIn."""
    tag_to_domain = {
        "apple": "utility",
        "notes": "utility",
        "reminders": "utility",
        "calendar": "utility",
        "music": "entertainment",
        "spotify": "entertainment",
        "git": "tech_coding",
        "sql": "tech_coding",
        "database": "tech_coding",
        "coding": "tech_coding",
        "development": "tech_coding",
        "stock": "finance_crypto",
        "trading": "finance_crypto",
        "crypto": "finance_crypto",
        "finance": "finance_crypto",
        "search": "web_search",
        "web": "web_search",
        "research": "science_research",
        "news": "knowledge_media",
        "productivity": "utility",
        "timer": "utility",
        "todo": "utility",
        "email": "utility",
        "slack": "utility",
        "pdf": "utility",
        "ocr": "utility",
        "document": "utility",
        "shopping": "shopping",
        "ecommerce": "shopping",
        "price": "shopping",
        "health": "medical",
        "fitness": "medical",
        "workout": "medical",
        "nutrition": "food",
        "weather": "geo_weather",
        "home": "utility",
        "homekit": "utility",
        "automation": "utility",
        "media": "entertainment",
        "video": "entertainment",
        "scraping": "web_search",
    }

    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower in tag_to_domain:
            return tag_to_domain[tag_lower]

    return "utility"


def compute_catalog_hash(capabilities: list[dict]) -> str:
    """Calcola hash del catalogo per change detection."""
    import hashlib

    # Ordina per nome per hash deterministico
    sorted_caps = sorted(capabilities, key=lambda x: x.get("name", ""))

    content = json.dumps(
        {
            "capabilities": [
                {
                    "name": c.get("name"),
                    "domain": c.get("domain"),
                    "type": c.get("type"),
                }
                for c in sorted_caps
            ]
        },
        sort_keys=True,
    )

    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_stored_hash(client) -> str | None:
    """Ottiene hash memorizzato nella collection."""
    try:
        results, _ = client.scroll(
            collection_name=COLLECTION,
            limit=1,
            with_payload=["_catalog_hash"],
        )

        if results and results[0].payload:
            return results[0].payload.get("_catalog_hash")
    except Exception:
        pass
    return None


async def ensure_collection(client):
    """Assicura che la collection esista."""
    collections = client.get_collections().collections

    if not any(c.name == COLLECTION for c in collections):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(
                size=1024,
                distance=models.Distance.COSINE,
            ),
        )
        print(f"✅ Collection {COLLECTION} creata")
    else:
        print(f"✅ Collection {COLLECTION} esiste")


async def index_capabilities(
    client,
    embedding_service,
    tools_only: bool = False,
    skills_only: bool = False,
    force: bool = False,
):
    """Esegue l'indicizzazione."""
    print("\n📦 Caricamento capabilities...")

    # Carica tools
    tools = []
    if not skills_only:
        print("\n🛠️ Caricando tools dai domini...")
        tools = load_domain_tools()
        print(f"   Totale tools: {len(tools)}")

    # Carica skills
    skills = []
    if not tools_only:
        print("\n🧩 Caricando skills...")
        skills = await load_skills()
        print(f"   Totale skills: {len(skills)}")

    # Combina
    all_capabilities = tools + skills
    print(f"\n📊 Totale capabilities: {len(all_capabilities)}")

    # Verifica hash
    current_hash = compute_catalog_hash(all_capabilities)
    stored_hash = get_stored_hash(client)

    if not force and stored_hash == current_hash:
        print(f"\n✅ Index già aggiornato (hash: {current_hash})")

        # Verifica count
        info = client.get_collection(COLLECTION)
        if info.points_count == len(all_capabilities):
            print(f"   Punti: {info.points_count}")
            return 0
        else:
            print(f"   ⚠️ Count mismatch: {info.points_count} vs {len(all_capabilities)}")

    print(f"\n🔄 Reindicizzazione (hash: {current_hash})...")

    # Prepara punti
    print("📝 Generazione embedding...")
    points = []

    for cap in all_capabilities:
        # Testo per embedding
        embed_text = build_sota_embed_text(
            name=cap["name"],
            description=cap["description"],
            domain=cap["domain"],
            cap_type=cap["type"],
            category=cap.get("category", ""),
            skill=cap.get("skill", ""),
            tags=cap.get("tags", []),
        )

        # Embedding
        vector = embedding_service.embed_query(embed_text)

        # Priority boost
        priority_boost = {
            ("tool", "static"): 1.3,
            ("skill", "crystallized"): 1.1,
            ("skill", "learned"): 0.9,
        }.get((cap["type"], cap.get("subtype", "")), 1.0)

        # Schema JSON
        schema_json = json.dumps(cap.get("schema", {}))

        point = models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "name": cap["name"],
                "type": cap["type"],
                "subtype": cap.get("subtype", ""),
                "domain": cap["domain"],
                "tenant_id": "me4brain_core",
                "text": embed_text,  # Required for LlamaIndex TextNode validation
                "category": cap.get("category", ""),
                "skill": cap.get("skill", ""),
                "description": cap["description"],
                "schema_json": schema_json,
                "tags": cap.get("tags", []),
                "skill_id": cap.get("skill_id", ""),
                "priority_boost": priority_boost,
                "enabled": True,
                "_catalog_hash": current_hash,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        points.append(point)

    # Elimina vecchi punti
    print("🗑️ Eliminazione vecchi punti...")
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass

    await ensure_collection(client)

    # Inserisci
    print(f"📥 Inserimento {len(points)} punti...")
    batch_size = 10

    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=COLLECTION, points=batch)

        if (i + batch_size) % 50 == 0 or i + batch_size >= len(points):
            print(f"   {min(i + batch_size, len(points))}/{len(points)}")

        gc.collect()

    # Verifica
    info = client.get_collection(COLLECTION)
    print(f"\n✅ Indicizzazione completata!")
    print(f"   Collection: {COLLECTION}")
    print(f"   Punti: {info.points_count}")
    print(f"   Hash: {current_hash}")

    # Statistiche
    tool_count = 0
    skill_count = 0
    domains = set()

    results, _ = client.scroll(
        collection_name=COLLECTION,
        limit=10000,
        with_payload=True,
    )

    for p in results:
        if p.payload.get("type") == "tool":
            tool_count += 1
        elif p.payload.get("type") == "skill":
            skill_count += 1
        if p.payload.get("domain"):
            domains.add(p.payload["domain"])

    print(f"\n📊 Statistiche:")
    print(f"   Tools: {tool_count}")
    print(f"   Skills: {skill_count}")
    print(f"   Domini: {len(domains)}")

    return 0


async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Indicizza tools e skills")
    parser.add_argument("--tools-only", action="store_true", help="Indicizza solo tools")
    parser.add_argument("--skills-only", action="store_true", help="Indicizza solo skills")
    parser.add_argument("--force", action="store_true", help="Forza reindicizzazione")
    args = parser.parse_args()

    print("=" * 60)
    print("🔧 INDICIZZAZIONE CAPABILITIES UNIFICATA")
    print("=" * 60)
    print(f"Collection: {COLLECTION}")

    if args.tools_only:
        print("Modalità: SOLO TOOLS")
    elif args.skills_only:
        print("Modalità: SOLO SKILLS")
    else:
        print("Modalità: TOOLS + SKILLS")

    # Client
    client = get_qdrant_client()

    # Embedding service
    from me4brain.embeddings import get_embedding_service

    embedding_service = get_embedding_service()
    print("✅ Embedding service (BGE-M3)")

    # Esegui indicizzazione
    return await index_capabilities(
        client,
        embedding_service,
        tools_only=args.tools_only,
        skills_only=args.skills_only,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
