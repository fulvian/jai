"""Unit tests per il sistema Skill - Parser, Types, Watcher."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from me4brain.core.skills.parser import SkillParser, SkillParseError
from me4brain.core.skills.types import (
    ExecutionTrace,
    Skill,
    SkillDefinition,
    ScoredSkill,
    ToolCall,
)


class TestToolCall:
    """Test per ToolCall model."""

    def test_create_basic_tool_call(self):
        """Test creazione ToolCall base."""
        tc = ToolCall(
            name="geo_weather",
            args={"city": "Roma"},
            result={"temp": 20},
            success=True,
            duration_ms=150.5,
        )
        assert tc.name == "geo_weather"
        assert tc.args["city"] == "Roma"
        assert tc.success is True
        assert tc.duration_ms == 150.5


class TestExecutionTrace:
    """Test per ExecutionTrace model."""

    def test_create_trace(self):
        """Test creazione ExecutionTrace."""
        trace = ExecutionTrace(
            session_id="test-session",
            input_query="Che tempo fa a Roma?",
            tool_chain=[
                ToolCall(name="geo_weather", args={"city": "Roma"}),
            ],
            success=True,
        )
        assert trace.session_id == "test-session"
        assert len(trace.tool_chain) == 1

    def test_trace_signature(self):
        """Test generazione signature."""
        trace = ExecutionTrace(
            session_id="test",
            input_query="test",
            tool_chain=[
                ToolCall(name="geo_weather", args={}),
                ToolCall(name="google_calendar", args={}),
            ],
        )
        # Signature è ordinata alfabeticamente
        assert trace.signature == "geo_weather:google_calendar"


class TestSkill:
    """Test per Skill model."""

    def test_create_explicit_skill(self):
        """Test creazione skill esplicita."""
        skill = Skill(
            id="test-skill-1",
            name="weather_alert",
            description="Invia alert meteo",
            type="explicit",
            code="# Istruzioni",
        )
        assert skill.type == "explicit"
        assert skill.enabled is True
        assert skill.usage_count == 0

    def test_success_rate_empty(self):
        """Test success_rate con zero usage."""
        skill = Skill(
            id="test",
            name="test",
            description="test",
            type="crystallized",
            code="{}",
        )
        # Prior neutro
        assert skill.success_rate == 0.5

    def test_success_rate_with_usage(self):
        """Test success_rate con usage."""
        skill = Skill(
            id="test",
            name="test",
            description="test",
            type="crystallized",
            code="{}",
            usage_count=10,
            success_count=8,
        )
        assert skill.success_rate == 0.8

    def test_confidence(self):
        """Test calcolo confidence."""
        skill = Skill(
            id="test",
            name="test",
            description="test",
            type="crystallized",
            code="{}",
            usage_count=0,
        )
        # 0 usage -> confidence 0
        assert skill.confidence == 0.0

        skill.usage_count = 1
        assert skill.confidence == 0.5

        skill.usage_count = 10
        assert skill.confidence > 0.9

    def test_record_usage(self):
        """Test registrazione usage."""
        skill = Skill(
            id="test",
            name="test",
            description="test",
            type="crystallized",
            code="{}",
        )
        skill.record_usage(success=True)
        assert skill.usage_count == 1
        assert skill.success_count == 1

        skill.record_usage(success=False)
        assert skill.usage_count == 2
        assert skill.failure_count == 1


class TestScoredSkill:
    """Test per ScoredSkill."""

    def test_from_skill(self):
        """Test creazione ScoredSkill."""
        skill = Skill(
            id="test",
            name="test",
            description="test",
            type="crystallized",
            code="{}",
            usage_count=10,
            success_count=8,
        )

        scored = ScoredSkill.from_skill(skill, similarity=0.9)

        assert scored.similarity_score == 0.9
        # weighted = similarity * success_rate * confidence
        # = 0.9 * 0.8 * ~0.91 ≈ 0.65
        assert scored.weighted_score > 0.6


class TestSkillParser:
    """Test per SkillParser."""

    def test_parse_valid_skill(self):
        """Test parsing skill valida."""
        content = """---
name: test_skill
description: Una skill di test
version: "1.0"
tags:
  - test
  - example
---

## Istruzioni

1. Fai questo
2. Poi quello
"""
        parser = SkillParser()
        skill_def = parser.parse_content(content)

        assert skill_def.name == "test_skill"
        assert skill_def.description == "Una skill di test"
        assert skill_def.version == "1.0"
        assert "test" in skill_def.tags
        assert "Istruzioni" in skill_def.instructions

    def test_parse_missing_frontmatter(self):
        """Test errore se manca frontmatter."""
        content = """# Solo markdown

Niente YAML qui.
"""
        parser = SkillParser()
        with pytest.raises(SkillParseError, match="Frontmatter"):
            parser.parse_content(content)

    def test_parse_missing_name(self):
        """Test errore se manca name."""
        content = """---
description: Solo description
---

Body
"""
        parser = SkillParser()
        with pytest.raises(SkillParseError, match="name"):
            parser.parse_content(content)

    def test_parse_file(self):
        """Test parsing da file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("""---
name: file_skill
description: Skill da file
---

Contenuto
""")
            f.flush()

            parser = SkillParser()
            skill_def = parser.parse_file(Path(f.name))

            assert skill_def.name == "file_skill"

    def test_parse_file_not_found(self):
        """Test errore file non trovato."""
        parser = SkillParser()
        with pytest.raises(SkillParseError, match="non trovato"):
            parser.parse_file(Path("/nonexistent/path.md"))

    def test_discover_skills(self):
        """Test discovery skill in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Crea sottodirectory con SKILL.md
            skill_dir = Path(tmpdir) / "my_skill"
            skill_dir.mkdir()

            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text("""---
name: discovered_skill
description: Auto-discovered
---

Body
""")

            parser = SkillParser()
            skills = parser.discover_skills(Path(tmpdir))

            assert len(skills) == 1
            assert skills[0].name == "discovered_skill"

    def test_discover_skills_empty_dir(self):
        """Test discovery in directory vuota."""
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = SkillParser()
            skills = parser.discover_skills(Path(tmpdir))
            assert skills == []

    def test_discover_skills_nonexistent_dir(self):
        """Test discovery in directory inesistente."""
        parser = SkillParser()
        skills = parser.discover_skills(Path("/nonexistent"))
        assert skills == []
