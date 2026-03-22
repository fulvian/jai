#!/usr/bin/env python3
"""Reindex all tools AND skills into Qdrant tools_and_skills collection.

This script:
1. Loads tool definitions from domain modules
2. Discovers and parses all skills (bundled + ClawHub)
3. Indexes everything with BGE-M3 embeddings for semantic retrieval
"""

import asyncio
import gc
import json
import sys
import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models
from qdrant_client.models import Filter, FieldCondition, MatchValue


COLLECTION = "tools_and_skills"
QDRANT_URL = "http://qdrant:6334"  # Inside Docker network

# For local testing
QDRANT_URL_LOCAL = "http://localhost:6334"


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client, trying Docker first, then localhost."""
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        client.get_collections()
        print(f"✅ Connected to Qdrant at {QDRANT_URL}")
        return client
    except Exception:
        client = QdrantClient(url=QDRANT_URL_LOCAL, timeout=60)
        client.get_collections()
        print(f"✅ Connected to Qdrant at {QDRANT_URL_LOCAL}")
        return client


def build_sota_embed_text(
    name: str,
    description: str,
    domain: str,
    tags: list[str] | None = None,
    item_type: str = "tool",
    category: str = "",
    skill: str = "",
) -> str:
    """Build SOTA 2026 template for optimal embedding retrieval.

    Template optimized for semantic search with BGE-M3.
    Includes:
    - [search_query]: prefix for BGE-M3
    - Hierarchical path (domain > category > skill)
    - "Use when user wants to" intent phrases
    - "NOT suitable for" disambiguation
    """
    tags_str = ", ".join(tags) if tags else ""

    # Build hierarchy path
    hierarchy_parts = [domain]
    if category:
        hierarchy_parts.append(category)
    if skill:
        hierarchy_parts.append(skill)
    hierarchy = " > ".join(hierarchy_parts)

    # Generate disambiguation hints based on common confusions
    not_suitable = _get_not_suitable_hints(name, domain, category)

    if item_type == "skill":
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


def _get_not_suitable_hints(name: str, domain: str, category: str) -> str:
    """Generate disambiguation hints for commonly confused tools."""
    hints = {
        # Gmail vs Drive
        "google_gmail_search": "searching files, Google Drive operations, document management",
        "google_gmail_get_message": "file content, Drive files, spreadsheets",
        "google_drive_search": "emails, email content, Gmail inbox",
        "google_drive_list_files": "email messages, Gmail, inbox",
        # Calendar vs Meet
        "google_calendar_upcoming": "video calls, meetings links, conference calls",
        "google_meet_create": "calendar events, scheduling, appointments",
        # Crypto vs Stocks
        "coingecko_price": "stock prices, equity trading, NYSE/NASDAQ",
        "binance_price": "stock quotes, traditional markets, forex",
        "yahoo_quote": "cryptocurrency, Bitcoin, Ethereum, altcoins",
        "finnhub_quote": "crypto prices, blockchain, DeFi",
        # Docs vs Sheets
        "google_docs_create": "spreadsheets, data tables, calculations",
        "google_sheets_create": "text documents, word processing, articles",
    }
    return hints.get(name, "")


def load_domain_tools() -> list[dict]:
    """Load all tool definitions from domains."""
    from me4brain.domains import (
        finance_crypto,
        google_workspace,
        medical,
        travel,
        web_search,
        geo_weather,
        food,
        sports_nba,
        sports_booking,
        tech_coding,
        science_research,
        knowledge_media,
        entertainment,
        jobs,
        utility,
    )

    domain_modules = [
        ("finance_crypto", "me4brain.domains.finance_crypto.tools.finance_api"),
        ("google_workspace", "me4brain.domains.google_workspace.tools.google_api"),
        ("medical", "me4brain.domains.medical.tools.medical_api"),
        ("travel", "me4brain.domains.travel.tools.travel_api"),
        ("web_search", "me4brain.domains.web_search.tools.search_api"),
        ("geo_weather", "me4brain.domains.geo_weather.tools.geo_api"),
        ("food", "me4brain.domains.food.tools.food_api"),
        ("sports_nba", "me4brain.domains.sports_nba.tools.nba_api"),
        ("sports_booking", "me4brain.domains.sports_booking.tools.playtomic_api"),
        ("tech_coding", "me4brain.domains.tech_coding.tools.tech_api"),
        ("science_research", "me4brain.domains.science_research.tools.science_api"),
        ("knowledge_media", "me4brain.domains.knowledge_media.tools.knowledge_api"),
        ("entertainment", "me4brain.domains.entertainment.tools.entertainment_api"),
        ("jobs", "me4brain.domains.jobs.tools.jobs_api"),
        ("utility", "me4brain.domains.utility.tools"),
    ]

    all_tools = []
    for domain_name, module_path in domain_modules:
        try:
            module = __import__(module_path, fromlist=["get_tool_definitions"])
            tools = module.get_tool_definitions()
            for tool in tools:
                all_tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "domain": tool.domain,  # Use domain from ToolDefinition!
                        "category": getattr(tool, "category", ""),
                        "type": "tool",
                        "subtype": "domain_tool",
                    }
                )
            print(f"   {domain_name}: {len(tools)} tools")
        except Exception as e:
            print(f"   ❌ {domain_name}: {e}")

    return all_tools


async def load_skills() -> list[dict]:
    """Load all skill definitions from bundled + ClawHub."""
    from me4brain.skills import SkillLoader, SkillRegistry

    loader = SkillLoader()
    registry = SkillRegistry(loader)
    await registry.initialize()

    skills = []
    for skill in registry.skills:
        # Determine domain based on tags
        domain = determine_skill_domain(skill.metadata.tags)

        skills.append(
            {
                "name": skill.name,
                "description": skill.description,
                "domain": domain,
                "tags": skill.metadata.tags,
                "type": "skill",
                "subtype": "clawhub_skill"
                if skill.id.startswith("local/") or skill.id.startswith("@")
                else "bundled_skill",
                "skill_id": skill.id,
                "instructions": skill.instructions[:500] if skill.instructions else "",
            }
        )

    return skills


def determine_skill_domain(tags: list[str]) -> str:
    """Map skill tags to Me4BrAIn domains."""
    tag_to_domain = {
        # Apple/macOS
        "apple": "utility",
        "notes": "utility",
        "reminders": "utility",
        "calendar": "utility",
        "music": "entertainment",
        "spotify": "entertainment",
        # Coding
        "git": "tech_coding",
        "sql": "tech_coding",
        "database": "tech_coding",
        "docker": "tech_coding",
        "coding": "tech_coding",
        "development": "tech_coding",
        # Finance
        "stock": "finance_crypto",
        "trading": "finance_crypto",
        "crypto": "finance_crypto",
        "finance": "finance_crypto",
        # Search/Research
        "search": "web_search",
        "web": "web_search",
        "research": "science_research",
        "news": "knowledge_media",
        # Productivity
        "productivity": "utility",
        "timer": "utility",
        "todo": "utility",
        "obsidian": "utility",
        # Communication
        "email": "utility",
        "slack": "utility",
        "communication": "utility",
        # Documents
        "pdf": "utility",
        "ocr": "utility",
        "document": "utility",
        # Shopping/E-commerce
        "shopping": "shopping",
        "ecommerce": "shopping",
        "price": "shopping",
        # Health
        "health": "medical",
        "fitness": "medical",
        "workout": "medical",
        "nutrition": "food",
        # Weather
        "weather": "geo_weather",
        # Home
        "home": "utility",
        "homekit": "utility",
        "automation": "utility",
        # Media
        "media": "entertainment",
        "video": "entertainment",
        "scraping": "web_search",
        # Marketplace/Second-hand Shopping
        "marketplace": "shopping",
        "subito": "shopping",
        "ebay": "shopping",
        "vinted": "shopping",
        "wallapop": "shopping",
        "amazon": "shopping",
        "used": "shopping",
        "secondhand": "shopping",
        "usato": "shopping",
        "reseller": "shopping",
    }

    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower in tag_to_domain:
            return tag_to_domain[tag_lower]

    return "utility"  # Default


def main():
    print("🔧 Tools & Skills Reindexing Script")
    print("=" * 60)

    # Connect to Qdrant
    client = get_qdrant_client()

    # Load embedding service
    from me4brain.embeddings import get_embedding_service

    emb = get_embedding_service()
    print("✅ Embedding service loaded (BGE-M3)")

    # Load tools
    print("\n📦 Loading tool definitions from domains...")
    tools = load_domain_tools()
    print(f"   Total tools: {len(tools)}")

    # Load skills
    print("\n🧩 Loading skill definitions...")
    skills = asyncio.run(load_skills())
    bundled = sum(1 for s in skills if s["subtype"] == "bundled_skill")
    clawhub = sum(1 for s in skills if s["subtype"] == "clawhub_skill")
    print(f"   Bundled skills: {bundled}")
    print(f"   ClawHub skills: {clawhub}")
    print(f"   Total skills: {len(skills)}")

    # Combine all items
    all_items = tools + skills
    print(f"\n📊 Total items to index: {len(all_items)}")

    # Recreate collection
    print(f"\n🗑️  Recreating collection {COLLECTION}...")
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE),
    )
    print(f"✅ Collection {COLLECTION} created")

    # Index in batches
    print(f"\n📥 Indexing {len(all_items)} items...")
    batch_size = 10
    total_indexed = 0

    for i in range(0, len(all_items), batch_size):
        batch = all_items[i : i + batch_size]
        points = []

        for item in batch:
            # Build embedding text
            text_content = build_sota_embed_text(
                name=item["name"],
                description=item["description"],
                domain=item["domain"],
                tags=item.get("tags"),
                item_type=item["type"],
            )

            # Generate embedding
            vector = emb.embed_query(text_content)

            # Build payload
            payload = {
                # LlamaIndex required fields
                "text": text_content,
                "_node_content": text_content,
                "_node_type": "TextNode",
                # Item metadata
                "tool_name": item["name"],  # Keep for backward compat
                "name": item["name"],
                "description": item["description"],
                "domain": item["domain"],
                "type": item["type"],
                "subtype": item["subtype"],
                "priority_boost": 1.3 if item["type"] == "tool" else 1.2,
            }

            # Add skill-specific fields
            if item["type"] == "skill":
                payload["skill_id"] = item.get("skill_id", "")
                payload["tags"] = item.get("tags", [])
                payload["instructions_preview"] = item.get("instructions", "")[:200]

            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload,
                )
            )

        # Upsert batch
        client.upsert(collection_name=COLLECTION, points=points)
        total_indexed += len(points)

        item_types = {}
        for p in points:
            t = p.payload["type"]
            item_types[t] = item_types.get(t, 0) + 1

        print(f"   Batch {i // batch_size + 1}: {item_types} (total: {total_indexed})")

        # Force garbage collection
        del points
        gc.collect()

    # Verify
    info = client.get_collection(COLLECTION)
    print(f"\n✅ Indexing complete!")
    print(f"   Collection: {COLLECTION}")
    print(f"   Points: {info.points_count}")

    # Stats by type
    tool_count = client.count(
        collection_name=COLLECTION,
        count_filter=Filter(must=[FieldCondition(key="type", match=MatchValue(value="tool"))]),
    ).count

    skill_count = client.count(
        collection_name=COLLECTION,
        count_filter=Filter(must=[FieldCondition(key="type", match=MatchValue(value="skill"))]),
    ).count

    print(f"\n📊 Index Stats:")
    print(f"   Tools: {tool_count}")
    print(f"   Skills: {skill_count}")
    print(f"   Total: {info.points_count}")

    if info.points_count != len(all_items):
        print(f"   ⚠️ Warning: Expected {len(all_items)}, got {info.points_count}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
