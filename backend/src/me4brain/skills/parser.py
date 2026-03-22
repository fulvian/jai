"""SKILL.md Parser.

Parses ClawHub-compatible SKILL.md files with YAML frontmatter
and markdown instructions body.

Format:
    ---
    name: Skill Name
    description: What this skill does
    disable-model-invocation: false
    metadata:
      requires:
        - cli: some-cli
        - env: API_KEY
    ---

    # Instructions

    When user asks "[trigger]", do [action].
"""

import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from me4brain.skills.types import (
    CLIRequirement,
    EnvRequirement,
    Requirement,
    SkillDefinition,
    SkillMetadata,
    SkillSource,
    SkillStatus,
)

logger = structlog.get_logger(__name__)

# Regex to match YAML frontmatter
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$",
    re.DOTALL,
)


class SkillParseError(Exception):
    """Error parsing SKILL.md file."""

    pass


class SkillParser:
    """Parser for ClawHub-compatible SKILL.md files."""

    def parse(self, skill_path: Path) -> SkillDefinition:
        """Parse a SKILL.md file into a SkillDefinition.

        Args:
            skill_path: Path to SKILL.md file

        Returns:
            Parsed SkillDefinition

        Raises:
            SkillParseError: If parsing fails
        """
        if not skill_path.exists():
            raise SkillParseError(f"SKILL.md not found: {skill_path}")

        content = skill_path.read_text(encoding="utf-8")
        return self.parse_content(content, skill_path)

    def parse_content(
        self,
        content: str,
        source_path: Path | None = None,
    ) -> SkillDefinition:
        """Parse SKILL.md content string.

        Args:
            content: Raw SKILL.md content
            source_path: Optional path for reference

        Returns:
            Parsed SkillDefinition
        """
        # Split frontmatter and body
        frontmatter, body = self._split_frontmatter(content)

        # Parse YAML frontmatter
        try:
            metadata_dict = yaml.safe_load(frontmatter)
            if not isinstance(metadata_dict, dict):
                raise SkillParseError("Frontmatter must be a YAML dictionary")
        except yaml.YAMLError as e:
            raise SkillParseError(f"Invalid YAML frontmatter: {e}")

        # Validate required fields
        if "name" not in metadata_dict:
            raise SkillParseError("Missing required field: name")
        if "description" not in metadata_dict:
            raise SkillParseError("Missing required field: description")

        # Parse requirements
        requirements = self._parse_requirements(metadata_dict.get("metadata", {}))

        # Build metadata
        metadata = SkillMetadata(
            name=metadata_dict["name"],
            description=metadata_dict["description"],
            version=metadata_dict.get("version", "1.0.0"),
            author=metadata_dict.get("author"),
            source=self._detect_source(source_path),
            tags=metadata_dict.get("tags", []),
            requires=requirements,
            disable_auto_invoke=metadata_dict.get("disable-model-invocation", False),
        )

        # Generate ID
        skill_id = self._generate_id(metadata, source_path)

        logger.info(
            "skill_parsed",
            skill_id=skill_id,
            name=metadata.name,
            requirements_count=len(requirements),
        )

        return SkillDefinition(
            id=skill_id,
            metadata=metadata,
            instructions=body.strip(),
            path=source_path,
            status=SkillStatus.DISCOVERED,
        )

    def _split_frontmatter(self, content: str) -> tuple[str, str]:
        """Split content into frontmatter and body.

        Args:
            content: Raw SKILL.md content

        Returns:
            Tuple of (frontmatter_yaml, body_markdown)
        """
        match = FRONTMATTER_PATTERN.match(content)
        if not match:
            raise SkillParseError(
                "Invalid SKILL.md format: missing YAML frontmatter. "
                "File must start with '---' followed by YAML content and another '---'"
            )

        return match.group(1), match.group(2)

    def _parse_requirements(self, metadata: dict[str, Any]) -> list[Requirement]:
        """Parse requirements from metadata section.

        Supports two formats:
        1. Standard: metadata.requires: [{cli: "curl"}, {env: "KEY"}]
        2. ClawHub:  metadata.clawdbot.requires: {bins: ["curl"], env: ["KEY"]}

        Args:
            metadata: The 'metadata' section from frontmatter

        Returns:
            List of Requirement objects
        """
        requirements: list[Requirement] = []

        # --- ClawHub nested format ---
        # e.g. {"clawdbot": {"requires": {"bins": ["curl", "python3"], "env": ["API_KEY"]}}}
        clawdbot = metadata.get("clawdbot", {})
        if isinstance(clawdbot, dict):
            clawdbot_requires = clawdbot.get("requires", {})
            if isinstance(clawdbot_requires, dict):
                for bin_name in clawdbot_requires.get("bins", []):
                    if isinstance(bin_name, str):
                        requirements.append(CLIRequirement(cli_name=bin_name))
                for env_name in clawdbot_requires.get("env", []):
                    if isinstance(env_name, str):
                        requirements.append(EnvRequirement(env_name=env_name))

                if requirements:
                    logger.debug(
                        "clawdbot_requirements_parsed",
                        bins=[r.cli_name for r in requirements if isinstance(r, CLIRequirement)],
                        envs=[r.env_name for r in requirements if isinstance(r, EnvRequirement)],
                    )

        # --- Standard format ---
        # e.g. {requires: [{cli: "curl"}, {env: "API_KEY"}]}
        for req in metadata.get("requires", []):
            if not isinstance(req, dict):
                continue

            if "cli" in req:
                requirements.append(
                    CLIRequirement(
                        cli_name=req["cli"],
                        min_version=req.get("min_version"),
                    )
                )
            elif "env" in req:
                requirements.append(
                    EnvRequirement(
                        env_name=req["env"],
                        secret=req.get("secret", True),
                    )
                )

        return requirements

    def _detect_source(self, path: Path | None) -> SkillSource:
        """Detect skill source from path.

        Args:
            path: Path to skill

        Returns:
            SkillSource enum value
        """
        if path is None:
            return SkillSource.GENERATED

        path_str = str(path).lower()

        if ".clawhub" in path_str or "clawhub" in path_str:
            return SkillSource.CLAWHUB
        elif "bundled" in path_str or "me4brain/skills/bundled" in path_str:
            return SkillSource.BUNDLED
        else:
            return SkillSource.LOCAL

    def _generate_id(
        self,
        metadata: SkillMetadata,
        path: Path | None,
    ) -> str:
        """Generate unique skill ID.

        Args:
            metadata: Skill metadata
            path: Optional path

        Returns:
            Unique skill identifier
        """
        if metadata.author:
            return f"@{metadata.author}/{metadata.name}"
        elif path:
            # Use parent directory name as namespace
            parent = path.parent.name
            return f"local/{parent}/{metadata.name}"
        else:
            return f"generated/{metadata.name}"
