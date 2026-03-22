"""Robust JSON parsing utilities for LLM responses."""

from __future__ import annotations

import json
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from json_repair import repair_json

    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False
    logger.debug("json_repair not available, using fallback parser")


def extract_json_from_markdown(content: str) -> str:
    """
    Extract JSON from markdown code blocks.

    Handles:
    - ```json ... ```
    - ``` ... ```
    - Raw JSON
    """
    content = content.strip()

    if "```json" in content:
        try:
            json_part = content.split("```json")[1].split("```")[0]
            return json_part.strip()
        except IndexError:
            pass

    if "```" in content:
        try:
            code_block = content.split("```")[1]
            if code_block.startswith("json"):
                code_block = code_block[4:]
            return code_block.strip()
        except IndexError:
            pass

    return content


def robust_json_parse(
    content: str,
    *,
    expect_array: bool = False,
    expect_object: bool = False,
) -> dict[str, Any] | list[Any] | None:
    """
    Parse JSON with multiple fallback strategies.

    Strategy:
    1. Try standard json.loads
    2. Extract from markdown and retry
    3. Use json_repair library if available
    4. Try to fix common issues manually

    Args:
        content: Raw string potentially containing JSON
        expect_array: If True, expect array as root
        expect_object: If True, expect object as root

    Returns:
        Parsed JSON as dict/list or None if all strategies fail
    """
    content = content.strip()
    if not content:
        return None

    parsed = _try_parse_direct(content)
    if parsed is not None and _validate_type(parsed, expect_array, expect_object):
        return parsed

    extracted = extract_json_from_markdown(content)
    if extracted != content:
        parsed = _try_parse_direct(extracted)
        if parsed is not None and _validate_type(parsed, expect_array, expect_object):
            return parsed

    if HAS_JSON_REPAIR:
        parsed = _try_json_repair(content)
        if parsed is not None and _validate_type(parsed, expect_array, expect_object):
            return parsed

    parsed = _try_manual_repair(content)
    if parsed is not None and _validate_type(parsed, expect_array, expect_object):
        return parsed

    logger.warning("json_parse_failed_all_strategies", extra={"content_preview": content[:200]})
    return None


def _try_parse_direct(content: str) -> dict[str, Any] | list[Any] | None:
    """Try direct json.loads."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _try_json_repair(content: str) -> dict[str, Any] | list[Any] | None:
    """Try json_repair library."""
    if not HAS_JSON_REPAIR:
        return None
    try:
        repaired = repair_json(content)
        return json.loads(repaired)
    except (json.JSONDecodeError, Exception) as e:
        logger.debug("json_repair_failed", extra={"error": str(e)})
        return None


def _try_manual_repair(content: str) -> dict[str, Any] | list[Any] | None:
    """
    Try to fix common JSON issues manually.

    Handles:
    - Trailing commas
    - Unquoted keys
    - Single quotes instead of double
    - Missing closing braces/brackets
    - Comments (// and /* */)
    - Excessive whitespace/indentation
    """
    repaired = content

    # Remove comments
    repaired = re.sub(r"//.*$", "", repaired, flags=re.MULTILINE)
    repaired = re.sub(r"/\*.*?\*/", "", repaired, flags=re.DOTALL)

    # Normalize whitespace: collapse multiple newlines and excessive spaces
    repaired = re.sub(r"\s*\n\s*", "", repaired)

    # Fix trailing commas
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r",\s*$", "", repaired)

    # Single quotes to double quotes
    repaired = repaired.replace("'", '"')

    # Unquoted keys
    repaired = re.sub(r"(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', repaired)

    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")

    if open_braces > 0:
        repaired += "}" * open_braces
    if open_brackets > 0:
        repaired += "]" * open_brackets

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _validate_type(parsed: Any, expect_array: bool, expect_object: bool) -> bool:
    """Validate that parsed JSON matches expected type."""
    if expect_array and not isinstance(parsed, list):
        return False
    if expect_object and not isinstance(parsed, dict):
        return False
    return True


def parse_llm_json_response(
    content: str,
    *,
    required_keys: list[str] | None = None,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Parse JSON from LLM response with validation.

    Args:
        content: Raw LLM response
        required_keys: Optional list of keys that must be present
        default: Default dict to return if parsing fails

    Returns:
        Parsed and validated dict, or default/empty dict on failure
    """
    if default is None:
        default = {}

    parsed = robust_json_parse(content, expect_object=True)

    if not isinstance(parsed, dict):
        logger.warning("llm_json_parse_invalid_type", extra={"type": type(parsed).__name__})
        return default

    if required_keys:
        missing = [k for k in required_keys if k not in parsed]
        if missing:
            logger.warning("llm_json_missing_keys", extra={"missing": missing})
            return default

    return parsed


def safe_json_loads(content: str) -> dict[str, Any] | list[Any] | None:
    """
    Simple wrapper for backward compatibility.
    Uses robust parsing with all strategies.
    """
    return robust_json_parse(content)
