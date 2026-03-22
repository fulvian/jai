"""Skill Types and Data Models.

Defines the core data structures for skills compatible with both
ClawHub SKILL.md format and native Python handlers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class SkillStatus(str, Enum):
    """Skill lifecycle status."""

    DISCOVERED = "discovered"  # Found but not loaded
    LOADING = "loading"  # Being loaded
    READY = "ready"  # Loaded and ready to use
    DISABLED = "disabled"  # Manually disabled
    ERROR = "error"  # Failed to load


class SkillSource(str, Enum):
    """Where the skill came from."""

    CLAWHUB = "clawhub"  # Downloaded from ClawHub registry
    LOCAL = "local"  # Local workspace skill
    BUNDLED = "bundled"  # Bundled with Me4BrAIn
    GENERATED = "generated"  # Auto-generated from user request


@dataclass
class Requirement(ABC):
    """Base class for skill requirements."""

    @abstractmethod
    def check(self) -> tuple[bool, str]:
        """Check if requirement is satisfied.

        Returns:
            Tuple of (is_satisfied, error_message)
        """
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        ...


@dataclass
class CLIRequirement(Requirement):
    """Requirement for a CLI tool to be available."""

    cli_name: str
    min_version: str | None = None

    def check(self) -> tuple[bool, str]:
        """Check if CLI is available in PATH."""
        import shutil

        if shutil.which(self.cli_name):
            return True, ""
        return False, f"CLI '{self.cli_name}' not found in PATH"

    def to_dict(self) -> dict[str, Any]:
        return {"cli": self.cli_name, "min_version": self.min_version}


@dataclass
class EnvRequirement(Requirement):
    """Requirement for an environment variable."""

    env_name: str
    secret: bool = True  # If True, use SecretsManager

    def check(self) -> tuple[bool, str]:
        """Check if environment variable is set."""
        import os

        if os.getenv(self.env_name):
            return True, ""
        return False, f"Environment variable '{self.env_name}' not set"

    def to_dict(self) -> dict[str, Any]:
        return {"env": self.env_name, "secret": self.secret}


@dataclass
class SkillMetadata:
    """Metadata extracted from SKILL.md frontmatter."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str | None = None
    source: SkillSource = SkillSource.LOCAL
    tags: list[str] = field(default_factory=list)
    requires: list[Requirement] = field(default_factory=list)
    disable_auto_invoke: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "source": self.source.value,
            "tags": self.tags,
            "requires": [r.to_dict() for r in self.requires],
            "disable_auto_invoke": self.disable_auto_invoke,
        }


@dataclass
class SkillDefinition:
    """Complete skill definition."""

    # Identity
    id: str  # Unique identifier (author/name or local path hash)
    metadata: SkillMetadata

    # Content
    instructions: str  # Markdown body from SKILL.md
    path: Path | None = None  # Local path if available

    # Runtime
    status: SkillStatus = SkillStatus.DISCOVERED
    error_message: str | None = None

    # Timestamps
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None

    # Integration
    registered_tool_id: str | None = None  # ID in ProceduralMemory

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def auto_invoke(self) -> bool:
        return not self.metadata.disable_auto_invoke

    def check_requirements(self) -> list[tuple[Requirement, bool, str]]:
        """Check all requirements.

        Returns:
            List of (requirement, is_satisfied, error_message)
        """
        results = []
        for req in self.metadata.requires:
            satisfied, error = req.check()
            results.append((req, satisfied, error))
        return results

    def all_requirements_met(self) -> bool:
        """Check if all requirements are satisfied."""
        return all(satisfied for _, satisfied, _ in self.check_requirements())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "metadata": self.metadata.to_dict(),
            "instructions": self.instructions[:500] + "..."
            if len(self.instructions) > 500
            else self.instructions,
            "path": str(self.path) if self.path else None,
            "status": self.status.value,
            "error_message": self.error_message,
            "discovered_at": self.discovered_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "registered_tool_id": self.registered_tool_id,
        }
