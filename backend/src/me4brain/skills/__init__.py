"""Skills Package for Me4BrAIn.

This package provides infrastructure for integrating ClawHub-compatible skills
and native Python skills into the Me4BrAIn cognitive system.

Architecture:
    - SkillParser: Parses SKILL.md files (ClawHub format)
    - SkillLoader: Discovers and loads skills from workspace
    - SkillRegistry: Manages skill lifecycle and dependencies
    - SkillExecutor: Executes skills with memory integration
    - SkillIntegrator: Bridges skills with HybridRouter

Skill Types:
    1. ClawHub Mode: SKILL.md files with YAML frontmatter
    2. Native Mode: Python modules with SkillHandler class

Integration Points:
    - ProceduralMemory: Skills register as tools
    - EpisodicMemory: Skill executions stored as episodes
    - SemanticMemory: Skill entities added to knowledge graph
"""

from me4brain.skills.executor import SkillExecutionResult, SkillExecutor, create_skill_executor
from me4brain.skills.integrator import (
    IntegrationStats,
    SkillIntegrator,
    integrate_skills_with_engine,
)
from me4brain.skills.loader import SkillLoader, ensure_skill_directories
from me4brain.skills.parser import SkillParseError, SkillParser
from me4brain.skills.registry import SkillRegistry
from me4brain.skills.types import (
    CLIRequirement,
    EnvRequirement,
    Requirement,
    SkillDefinition,
    SkillMetadata,
    SkillSource,
    SkillStatus,
)

__all__ = [
    # Types
    "SkillDefinition",
    "SkillMetadata",
    "SkillStatus",
    "SkillSource",
    "Requirement",
    "CLIRequirement",
    "EnvRequirement",
    # Parser
    "SkillParser",
    "SkillParseError",
    # Loader
    "SkillLoader",
    "ensure_skill_directories",
    # Registry
    "SkillRegistry",
    # Executor
    "SkillExecutor",
    "SkillExecutionResult",
    "create_skill_executor",
    # Integrator
    "SkillIntegrator",
    "IntegrationStats",
    "integrate_skills_with_engine",
]
