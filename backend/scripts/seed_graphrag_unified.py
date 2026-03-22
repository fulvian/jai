#!/usr/bin/env python3
"""
Seed GraphRAG Unified (SOTA 2026).
Sincronizza i template di dominio, tool e few-shot examples in Neo4j.
Usa BGE-M3 (1024 dim) per gli embedding dei few-shot (Layer III).
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from neo4j import AsyncGraphDatabase

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from me4brain.embeddings.bge_m3 import get_embedding_service

# Neo4j Config
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_secret")

# Paths
CORE_CONFIG_DIR = PROJECT_ROOT / "config" / "prompt_hints"
DOMAINS_DIR = CORE_CONFIG_DIR / "domains"


def load_all_data() -> dict[str, Any]:
    """Carica tutti i file YAML dai domini SOTA 2026."""
    all_domains = {}
    for yaml_file in DOMAINS_DIR.glob("*.yaml"):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    all_domains[yaml_file.stem] = data
        except Exception as e:
            print(f"Warning: Could not load {yaml_file.name}: {e}")
    return all_domains


async def initialize_schema(session):
    """Inizializza indici e constraints in Neo4j."""
    print("Initializing Neo4j schemas...")
    # Node Constraints
    await session.run(
        "CREATE CONSTRAINT domain_name IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE"
    )
    await session.run("CREATE CONSTRAINT tool_id IF NOT EXISTS FOR (t:Tool) REQUIRE t.id IS UNIQUE")
    await session.run(
        "CREATE CONSTRAINT fewshot_id IF NOT EXISTS FOR (e:FewShotExample) REQUIRE e.id IS UNIQUE"
    )

    # Vector Index (Layer III retrieval)
    # NOTE: BGE-M3 = 1024 dimensions

    # 1. Drop existing index to prevent 1536 vs 1024 dimension mismatch
    await session.run("DROP INDEX fewshot_embeddings IF EXISTS")

    # 2. Recreate index with 1024 dimensions
    await session.run(
        """
        CREATE VECTOR INDEX fewshot_embeddings IF NOT EXISTS
        FOR (e:FewShotExample) ON (e.embedding)
        OPTIONS {indexConfig: {
         `vector.dimensions`: 1024,
         `vector.similarity_function`: 'cosine'
        }}
        """
    )
    print("Schema initialized.")


async def seed_graphrag():
    """Processo principale di seeding."""
    print("Starting unified GraphRAG seeding (SOTA 2026 format)...")

    embedding_service = get_embedding_service()
    domain_configs = load_all_data()

    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    async with driver.session() as session:
        await initialize_schema(session)

        for domain_name, config in domain_configs.items():
            print(f"Seeding Domain: {domain_name}")

            # 1. Domain Node
            await session.run(
                """
                MERGE (d:Domain {name: $name})
                SET d.description = $description,
                    d.constraints = $constraints,
                    d.hard_rules = $hard_rules,
                    d.updated_at = $now
                """,
                {
                    "name": domain_name,
                    "description": config.get("description", ""),
                    "constraints": str(config.get("constraints", {})),
                    "hard_rules": config.get("hard_rules", ""),
                    "now": datetime.now(timezone.utc).isoformat(),
                },
            )

            # 2. Tools
            tools = config.get("tools", {})
            for tool_id, tool_data in tools.items():
                print(f"  Seeding Tool: {tool_id}")
                await session.run(
                    """
                    MATCH (d:Domain {name: $domain_name})
                    MERGE (t:Tool {id: $tool_id})
                    SET t.name = $tool_id,
                        t.description = $description,
                        t.parameters = $parameters,
                        t.updated_at = $now
                    MERGE (d)-[:HAS_TOOL]->(t)
                    """,
                    {
                        "domain_name": domain_name,
                        "tool_id": tool_id,
                        "description": tool_data.get("description", ""),
                        "parameters": str(tool_data.get("parameters", {})),
                        "now": datetime.now(timezone.utc).isoformat(),
                    },
                )

                # 3. Few-shot Examples (Semantic memory for tool choosing)
                few_shots = tool_data.get("few_shot_examples", [])
                for i, fs in enumerate(few_shots):
                    fs_desc = ""
                    fs_content = ""
                    if isinstance(fs, str):
                        fs_desc = fs
                        fs_content = fs
                    else:
                        fs_desc = fs.get("description", fs.get("content", ""))
                        fs_content = fs.get("content", "")

                    print(f"    -> Embedding few-shot {i + 1}...")
                    embedding = await embedding_service.embed_document_async(fs_desc)

                    await session.run(
                        """
                        MATCH (t:Tool {id: $tool_id})
                        MERGE (e:FewShotExample {id: $example_id})
                        SET e.description = $description,
                            e.content = $content,
                            e.embedding = $embedding,
                            e.updated_at = $now
                        MERGE (t)-[:HAS_EXAMPLE]->(e)
                        """,
                        {
                            "tool_id": tool_id,
                            "example_id": f"fs_{tool_id}_{i}",
                            "description": fs_desc,
                            "content": fs_content,
                            "embedding": embedding,
                            "now": datetime.now(timezone.utc).isoformat(),
                        },
                    )

    await driver.close()
    print("Unified GraphRAG Seeding completed.")


if __name__ == "__main__":
    asyncio.run(seed_graphrag())
