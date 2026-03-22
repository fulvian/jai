#!/usr/bin/env python3
"""
Seed Manual Templates into Neo4j for Hand-Crafted PromptRAG.
Processes Domain, Category, and Tool YAMLs to build a hierarchical knowledge graph.
"""

import asyncio
import os
import yaml
from pathlib import Path
from typing import Any

import structlog
from me4brain.memory.semantic import get_semantic_memory

logger = structlog.get_logger(__name__)

# Paths
BASE_DIR = Path("/Users/fulvioventura/me4brain/config/prompt_hints")
DOMAINS_DIR = BASE_DIR / "domains"
CATEGORIES_DIR = BASE_DIR / "skill_categories"
TOOLS_DIR = BASE_DIR / "tools"


async def initialize_schema(session):
    """Ensure basic constraints for PromptRAG nodes."""
    constraints = [
        "CREATE CONSTRAINT domain_template_id IF NOT EXISTS FOR (d:DomainTemplate) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT category_template_id IF NOT EXISTS FOR (c:CategoryTemplate) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT tool_template_id IF NOT EXISTS FOR (t:ToolTemplate) REQUIRE t.id IS UNIQUE",
    ]
    for c in constraints:
        await session.run(c)


async def seed_domains(session):
    """Seed DomainTemplate nodes."""
    if not DOMAINS_DIR.exists():
        return
    for f in DOMAINS_DIR.glob("*.yaml"):
        with open(f, "r") as stream:
            data = yaml.safe_load(stream)
            domain_id = data.get("domain") or f.stem
            content = data.get("hints", "")
            logger.info("seeding_domain", id=domain_id)
            await session.run(
                "MERGE (d:DomainTemplate {id: $id}) SET d.content = $content",
                {"id": domain_id, "content": content},
            )


async def seed_tools(session):
    """Seed ToolTemplate nodes and link to Domains."""
    if not TOOLS_DIR.exists():
        return
    for f in TOOLS_DIR.glob("*.yaml"):
        with open(f, "r") as stream:
            data = yaml.safe_load(stream)
            tool_id = data.get("tool_id") or f.stem
            domain_id = data.get("domain")

            # Constraints and rules as JSON string for graph properties
            constraints = data.get("constraints", {})
            hard_rules = data.get("hard_rules", "")

            logger.info("seeding_tool", id=tool_id, domain=domain_id)

            # Create/Update Tool node
            await session.run(
                """
                MERGE (t:ToolTemplate {id: $id})
                SET t.content = $content,
                    t.constraints = $constraints,
                    t.hard_rules = $hard_rules
                """,
                {
                    "id": tool_id,
                    "content": data.get("description", ""),
                    "constraints": yaml.dump(constraints),
                    "hard_rules": hard_rules,
                },
            )

            # Link to Domain if present
            if domain_id:
                await session.run(
                    """
                    MATCH (t:ToolTemplate {id: $tool_id})
                    MATCH (d:DomainTemplate {id: $domain_id})
                    MERGE (t)-[:INHERITS_FROM]->(d)
                    """,
                    {"tool_id": tool_id, "domain_id": domain_id},
                )


async def main():
    semantic = get_semantic_memory()
    driver = await semantic.get_driver()
    if not driver:
        logger.error("neo4j_driver_not_found")
        return

    async with driver.session() as session:
        logger.info("starting_seeding_manual_templates")
        await initialize_schema(session)
        await seed_domains(session)
        await seed_tools(session)
        logger.info("seeding_completed")


if __name__ == "__main__":
    asyncio.run(main())
