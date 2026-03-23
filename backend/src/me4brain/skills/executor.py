"""Skill Executor.

Executes skills based on their instructions and type.
Handles different skill types:
- CLI-based skills (osascript, shell commands)
- API-based skills (HTTP requests)
- Python-based skills (native handlers)
"""

import asyncio
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from me4brain.secrets import get_secrets_manager
from me4brain.skills.types import SkillDefinition

logger = structlog.get_logger(__name__)


@dataclass
class SkillExecutionResult:
    """Result from skill execution."""

    success: bool
    data: dict[str, Any]
    error: str | None = None
    execution_time_ms: float = 0.0
    skill_id: str = ""


class SkillExecutor:
    """Executes skills based on their type and requirements."""

    def __init__(self, skill: SkillDefinition):
        """Initialize executor for a skill.

        Args:
            skill: Skill to execute
        """
        self.skill = skill
        self.secrets = get_secrets_manager()

    async def execute(
        self,
        query: str,
        options: dict[str, Any] | None = None,
    ) -> SkillExecutionResult:
        """Execute the skill.

        Args:
            query: User query/request
            options: Optional parameters

        Returns:
            Execution result
        """
        start_time = datetime.utcnow()

        try:
            # Determine execution method based on skill requirements
            if self._has_cli_requirement("osascript"):
                result = await self._execute_applescript(query, options)
            elif self._has_cli_requirement("screencapture"):
                result = await self._execute_screenshot(query, options)
            elif self._has_cli_requirement("pbcopy") or self._has_cli_requirement("pbpaste"):
                result = await self._execute_clipboard(query, options)
            elif self._has_cli_requirement("curl"):
                result = await self._execute_curl_skill(query, options)
            else:
                # Default: use instructions as prompt context
                result = await self._execute_generic(query, options)

            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            result.execution_time_ms = elapsed_ms
            result.skill_id = self.skill.id

            logger.info(
                "skill_executed",
                skill_id=self.skill.id,
                success=result.success,
                elapsed_ms=elapsed_ms,
            )

            return result

        except Exception as e:
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            logger.error(
                "skill_execution_error",
                skill_id=self.skill.id,
                error=str(e),
            )

            return SkillExecutionResult(
                success=False,
                data={},
                error=str(e),
                execution_time_ms=elapsed_ms,
                skill_id=self.skill.id,
            )

    def _has_cli_requirement(self, cli_name: str) -> bool:
        """Check if skill requires a specific CLI."""
        from me4brain.skills.types import CLIRequirement

        for req in self.skill.metadata.requires:
            if isinstance(req, CLIRequirement) and req.cli_name == cli_name:
                return True
        return False

    async def _execute_applescript(
        self,
        query: str,
        options: dict[str, Any] | None,
    ) -> SkillExecutionResult:
        """Execute AppleScript-based skill (Notes, Reminders)."""
        skill_name = self.skill.metadata.name.lower()

        if "notes" in skill_name:
            return await self._execute_apple_notes(query, options)
        elif "reminders" in skill_name:
            return await self._execute_apple_reminders(query, options)

        return SkillExecutionResult(
            success=False,
            data={},
            error="Unknown AppleScript skill type",
        )

    async def _execute_apple_notes(
        self,
        query: str,
        options: dict[str, Any] | None,
    ) -> SkillExecutionResult:
        """Execute Apple Notes operations."""
        (options or {}).get("action", "list")

        if "search" in query.lower() or "find" in query.lower():
            # Search notes
            script = """
            tell application "Notes"
                set noteList to {}
                repeat with n in notes of default account
                    set end of noteList to {name of n, body of n}
                end repeat
                return noteList
            end tell
            """
        else:
            # List notes
            script = """
            tell application "Notes"
                set noteList to {}
                repeat with n in notes of default account
                    set end of noteList to name of n
                end repeat
                return noteList
            end tell
            """

        try:
            result = await self._run_osascript(script)
            return SkillExecutionResult(
                success=True,
                data={"notes": result, "query": query},
            )
        except Exception as e:
            return SkillExecutionResult(
                success=False,
                data={},
                error=str(e),
            )

    async def _execute_apple_reminders(
        self,
        query: str,
        options: dict[str, Any] | None,
    ) -> SkillExecutionResult:
        """Execute Apple Reminders operations."""
        script = """
        tell application "Reminders"
            set reminderList to {}
            repeat with r in reminders
                if completed of r is false then
                    set end of reminderList to name of r
                end if
            end repeat
            return reminderList
        end tell
        """

        try:
            result = await self._run_osascript(script)
            return SkillExecutionResult(
                success=True,
                data={"reminders": result, "query": query},
            )
        except Exception as e:
            return SkillExecutionResult(
                success=False,
                data={},
                error=str(e),
            )

    async def _execute_screenshot(
        self,
        query: str,
        options: dict[str, Any] | None,
    ) -> SkillExecutionResult:
        """Execute screenshot capture."""
        from pathlib import Path

        # Determine output path
        output_dir = Path.home() / "Desktop"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"screenshot_{timestamp}.png"

        try:
            # Run screencapture
            cmd = ["screencapture", "-x", str(output_path)]

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, timeout=30),
            )

            if result.returncode == 0:
                return SkillExecutionResult(
                    success=True,
                    data={
                        "path": str(output_path),
                        "message": f"Screenshot saved to {output_path}",
                    },
                )
            else:
                return SkillExecutionResult(
                    success=False,
                    data={},
                    error=f"screencapture failed: {result.stderr.decode()}",
                )

        except Exception as e:
            return SkillExecutionResult(
                success=False,
                data={},
                error=str(e),
            )

    async def _execute_clipboard(
        self,
        query: str,
        options: dict[str, Any] | None,
    ) -> SkillExecutionResult:
        """Execute clipboard operations."""
        action = "get"
        if "copy" in query.lower():
            action = "set"

        try:
            loop = asyncio.get_event_loop()

            if action == "get":
                result = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        ["pbpaste"],
                        capture_output=True,
                        text=True,
                    ),
                )
                return SkillExecutionResult(
                    success=True,
                    data={"clipboard": result.stdout},
                )
            else:
                # Set clipboard (need text from options or query)
                text = (options or {}).get("text", query)
                result = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        ["pbcopy"],
                        input=text.encode(),
                        capture_output=True,
                    ),
                )
                return SkillExecutionResult(
                    success=True,
                    data={"copied": text},
                )

        except Exception as e:
            return SkillExecutionResult(
                success=False,
                data={},
                error=str(e),
            )

    async def _execute_curl_skill(
        self,
        query: str,
        options: dict[str, Any] | None,
    ) -> SkillExecutionResult:
        """Execute curl-based skill (marketplace search, web scraping).

        Parses instructions for {query} placeholders and executes.
        """
        import urllib.parse

        try:
            # URL-encode the query for safe use in URLs
            encoded_query = urllib.parse.quote(query)

            # Get instructions and substitute placeholders
            instructions = self.skill.instructions

            # Look for executable command blocks in instructions
            # Format: ```bash\n<command>\n```
            import re

            bash_blocks = re.findall(r"```(?:bash|sh)?\n(.+?)\n```", instructions, re.DOTALL)

            if bash_blocks:
                # Use the first bash block as the command
                command = bash_blocks[0].strip()
            else:
                # Fallback: try to find a curl command in instructions
                curl_match = re.search(r"(curl\s+[^\n]+)", instructions)
                if curl_match:
                    command = curl_match.group(1)
                else:
                    return SkillExecutionResult(
                        success=False,
                        data={},
                        error="No executable command found in skill instructions",
                    )

            # Substitute placeholders
            command = command.replace("{query}", encoded_query)
            command = command.replace("$QUERY", encoded_query)
            command = command.replace("${query}", encoded_query)

            # Also substitute raw query for non-URL contexts
            command = command.replace("{raw_query}", query)

            logger.debug(
                "curl_skill_executing",
                skill_name=self.skill.name,
                command_preview=command[:100],
            )

            # Execute command
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=45,
                ),
            )

            if result.returncode == 0:
                # Try to parse as JSON
                output = result.stdout.strip()
                try:
                    import json

                    data = json.loads(output)
                except json.JSONDecodeError:
                    # Truncate raw output to prevent flooding LLM context
                    MAX_RAW_OUTPUT = 10_000  # 10KB max
                    if len(output) > MAX_RAW_OUTPUT:
                        logger.warning(
                            "curl_skill_output_truncated",
                            skill_name=self.skill.name,
                            original_size=len(output),
                            truncated_to=MAX_RAW_OUTPUT,
                        )
                        output = (
                            output[:MAX_RAW_OUTPUT] + f"\n... [truncated from {len(output)} chars]"
                        )
                    data = {"raw_output": output}

                return SkillExecutionResult(
                    success=True,
                    data={
                        "query": query,
                        "skill": self.skill.name,
                        "results": data,
                    },
                )
            else:
                return SkillExecutionResult(
                    success=False,
                    data={},
                    error=f"Command failed: {result.stderr or 'Unknown error'}",
                )

        except subprocess.TimeoutExpired:
            return SkillExecutionResult(
                success=False,
                data={},
                error="Command timed out after 45 seconds",
            )
        except Exception as e:
            return SkillExecutionResult(
                success=False,
                data={},
                error=str(e),
            )

    async def _execute_generic(
        self,
        query: str,
        options: dict[str, Any] | None,
    ) -> SkillExecutionResult:
        """Generic execution using skill instructions as context.

        WARNING: This does NOT execute any real commands. It only returns
        the skill's instructions as context for the LLM. Results from this
        method should NOT be treated as real data.
        """
        return SkillExecutionResult(
            success=True,
            data={
                "_meta": {
                    "type": "instructions_only",
                    "warning": "No real data fetched. Skill fell back to generic execution. "
                    "Do NOT invent results, listings, or URLs based on these instructions.",
                },
                "skill_id": self.skill.id,
                "instructions": self.skill.instructions,
                "query": query,
                "message": f"Skill '{self.skill.name}' executed with query: {query}",
            },
        )

    async def _run_osascript(self, script: str) -> str:
        """Run AppleScript and return result."""
        loop = asyncio.get_event_loop()

        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30,
            ),
        )

        if result.returncode != 0:
            raise RuntimeError(f"osascript failed: {result.stderr}")

        return result.stdout.strip()


def create_skill_executor(skill: SkillDefinition) -> Callable:
    """Create an executor function for a skill.

    Args:
        skill: Skill definition

    Returns:
        Async callable that executes the skill
    """
    executor = SkillExecutor(skill)

    # Known parameter names the LLM may use instead of 'query'
    _QUERY_ALIASES: frozenset[str] = frozenset(
        {
            "query",
            "search_query",
            "keyword",
            "keywords",
            "search",
            "q",
            "product",
            "term",
            "text",
            "input",
        }
    )

    async def execute_skill(**kwargs: Any) -> dict[str, Any]:
        """Execute skill, accepting arbitrary kwargs from the ToolExecutor.

        The LLM router may send arguments with various parameter names
        (e.g., 'search_query', 'keyword', 'product'). This function
        maps them to the 'query' parameter expected by SkillExecutor.
        """
        # Extract query: try known aliases first, then fall back to first string value
        query = ""
        options = kwargs.pop("options", None)

        for alias in _QUERY_ALIASES:
            if alias in kwargs:
                query = str(kwargs.pop(alias))
                break

        # If no known alias matched, use the first string-valued argument
        if not query:
            for _key, value in list(kwargs.items()):
                if isinstance(value, str) and value:
                    query = value
                    break

        # Pass remaining kwargs as options if no explicit options provided
        if not options and kwargs:
            options = kwargs

        result = await executor.execute(query, options)
        if result.success:
            return result.data
        else:
            return {"error": result.error, "success": False}

    return execute_skill
