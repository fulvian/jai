#!/usr/bin/env python3
"""
Standalone Seed Manual Templates into Neo4j for Hand-Crafted PromptRAG.
Uses only 'neo4j' and 'PyYAML' libraries.
"""

import os
import yaml
from pathlib import Path
from neo4j import GraphDatabase

# Neo4j Settings (Hardcoded from .env for standalone execution)
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j_secret"

# Paths
BASE_DIR = Path("/Users/fulvioventura/me4brain/config/prompt_hints")
DOMAINS_DIR = BASE_DIR / "domains"
TOOLS_DIR = BASE_DIR / "tools"


def initialize_schema(tx):
    print("Initializing Neo4j schemas...")
    tx.run(
        "CREATE CONSTRAINT domain_template_id IF NOT EXISTS FOR (d:DomainTemplate) REQUIRE d.id IS UNIQUE"
    )
    tx.run(
        "CREATE CONSTRAINT tool_template_id IF NOT EXISTS FOR (t:ToolTemplate) REQUIRE t.id IS UNIQUE"
    )


def seed_domains(tx):
    if not DOMAINS_DIR.exists():
        return
    for f in DOMAINS_DIR.glob("*.yaml"):
        with open(f, "r") as stream:
            try:
                data = yaml.safe_load(stream)
                domain_id = data.get("domain") or f.stem
                content = data.get("hints", "")
                print(f"Seeding Domain: {domain_id}")
                tx.run(
                    "MERGE (d:DomainTemplate {id: $id}) SET d.content = $content",
                    {"id": domain_id, "content": content},
                )
            except Exception as e:
                print(f"Error seeding domain {f.name}: {e}")


def seed_tools(tx):
    if not TOOLS_DIR.exists():
        return
    for f in TOOLS_DIR.glob("*.yaml"):
        with open(f, "r") as stream:
            try:
                data = yaml.safe_load(stream)
                tool_id = data.get("tool_id") or f.stem
                domain_id = data.get("domain")

                constraints = data.get("constraints", {})
                hard_rules = data.get("hard_rules", "")

                print(f"Seeding Tool: {tool_id} (Domain: {domain_id})")

                tx.run(
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

                if domain_id:
                    tx.run(
                        """
                        MATCH (t:ToolTemplate {id: $tool_id})
                        MATCH (d:DomainTemplate {id: $domain_id})
                        MERGE (t)-[:INHERITS_FROM]->(d)
                        """,
                        {"tool_id": tool_id, "domain_id": domain_id},
                    )
            except Exception as e:
                print(f"Error seeding tool {f.name}: {e}")


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        print("Starting seeding process (standalone)...")
        session.execute_write(initialize_schema)
        session.execute_write(seed_domains)
        session.execute_write(seed_tools)
        print("Seeding completed successfully.")
    driver.close()


if __name__ == "__main__":
    main()
