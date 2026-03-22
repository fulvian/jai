"""Skill System - Init module."""

from me4brain.core.skills.crystallizer import Crystallizer
from me4brain.core.skills.monitor import ExecutionMonitor
from me4brain.core.skills.parser import SkillParser, SkillParseError
from me4brain.core.skills.registry_deprecated import SkillRegistry
from me4brain.core.skills.retriever import SkillRetriever
from me4brain.core.skills.types import (
    ExecutionTrace,
    Skill,
    SkillDefinition,
    SkillStats,
    ScoredSkill,
    ToolCall,
    VerificationResult,
)
from me4brain.core.skills.verifier import SkillVerifier
from me4brain.core.skills.watcher import SkillWatcher

# New modules for skill autogeneration
from me4brain.core.skills.approval import (
    SkillApprovalManager,
    PendingSkill,
    ApprovalStatus,
    get_skill_approval_manager,
)
from me4brain.core.skills.security import (
    SkillSecurityValidator,
    RiskLevel,
    SecurityValidationResult,
    get_skill_security_validator,
)
from me4brain.core.skills.persistence import (
    persist_skill_to_disk,
    delete_skill_from_disk,
    list_persisted_skills,
    skill_to_markdown,
)

__all__ = [
    # Types
    "ExecutionTrace",
    "Skill",
    "SkillDefinition",
    "SkillStats",
    "ScoredSkill",
    "ToolCall",
    "VerificationResult",
    # Components
    "Crystallizer",
    "ExecutionMonitor",
    "SkillParser",
    "SkillParseError",
    "SkillRegistry",
    "SkillRetriever",
    "SkillVerifier",
    "SkillWatcher",
    # Approval system
    "SkillApprovalManager",
    "PendingSkill",
    "ApprovalStatus",
    "get_skill_approval_manager",
    # Security
    "SkillSecurityValidator",
    "RiskLevel",
    "SecurityValidationResult",
    "get_skill_security_validator",
    # Persistence
    "persist_skill_to_disk",
    "delete_skill_from_disk",
    "list_persisted_skills",
    "skill_to_markdown",
]
