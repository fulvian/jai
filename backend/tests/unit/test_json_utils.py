"""Tests for json_utils module."""

import pytest

from me4brain.utils.json_utils import (
    extract_json_from_markdown,
    robust_json_parse,
    parse_llm_json_response,
    safe_json_loads,
)


class TestExtractJsonFromMarkdown:
    """Tests for extract_json_from_markdown function."""

    def test_extract_from_json_block(self):
        """Extract JSON from ```json code block."""
        content = '```json\n{"key": "value"}\n```'
        result = extract_json_from_markdown(content)
        assert result == '{"key": "value"}'

    def test_extract_from_plain_block(self):
        """Extract JSON from ``` code block."""
        content = '```\n{"key": "value"}\n```'
        result = extract_json_from_markdown(content)
        assert result == '{"key": "value"}'

    def test_return_raw_if_no_block(self):
        """Return raw content if no code block."""
        content = '{"key": "value"}'
        result = extract_json_from_markdown(content)
        assert result == '{"key": "value"}'

    def test_handle_empty_content(self):
        """Handle empty content."""
        assert extract_json_from_markdown("") == ""
        assert extract_json_from_markdown("   ").strip() == ""


class TestRobustJsonParse:
    """Tests for robust_json_parse function."""

    def test_parse_valid_json(self):
        """Parse valid JSON directly."""
        content = '{"name": "test", "value": 123}'
        result = robust_json_parse(content)
        assert result == {"name": "test", "value": 123}

    def test_parse_markdown_wrapped_json(self):
        """Parse JSON wrapped in markdown."""
        content = '```json\n{"name": "test"}\n```'
        result = robust_json_parse(content)
        assert result == {"name": "test"}

    def test_parse_json_with_trailing_comma(self):
        """Parse JSON with trailing comma (manual repair)."""
        content = '{"items": [1, 2, 3,]}'
        result = robust_json_parse(content)
        assert result == {"items": [1, 2, 3]}

    def test_parse_empty_returns_none(self):
        """Return None for empty content."""
        assert robust_json_parse("") is None
        assert robust_json_parse("   ") is None

    def test_parse_invalid_returns_none(self):
        """Return None for completely invalid content."""
        assert robust_json_parse("not json at all") is None

    def test_expect_array(self):
        """Validate expected array type."""
        content = "[1, 2, 3]"
        result = robust_json_parse(content, expect_array=True, expect_object=False)
        assert result == [1, 2, 3]

        # Object should fail when expecting array
        result = robust_json_parse('{"key": "value"}', expect_array=True, expect_object=False)
        assert result is None

    def test_expect_object(self):
        """Validate expected object type."""
        content = '{"key": "value"}'
        result = robust_json_parse(content, expect_object=True)
        assert result == {"key": "value"}


class TestParseLlmJsonResponse:
    """Tests for parse_llm_json_response function."""

    def test_parse_with_required_keys(self):
        """Parse with required key validation."""
        content = '{"intent": "search", "domains": ["web"]}'
        result = parse_llm_json_response(content, required_keys=["intent"])
        assert result == {"intent": "search", "domains": ["web"]}

    def test_missing_required_key_returns_default(self):
        """Return default when required key is missing."""
        content = '{"domains": ["web"]}'
        result = parse_llm_json_response(
            content,
            required_keys=["intent"],
            default={"intent": "unknown"},
        )
        assert result == {"intent": "unknown"}

    def test_invalid_json_returns_default(self):
        """Return default for invalid JSON."""
        result = parse_llm_json_response(
            "not json",
            default={"fallback": True},
        )
        assert result == {"fallback": True}


class TestSafeJsonLoads:
    """Tests for safe_json_loads function."""

    def test_parse_valid_json(self):
        """Parse valid JSON."""
        result = safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_invalid_returns_none(self):
        """Return None for invalid JSON."""
        assert safe_json_loads("invalid") is None
