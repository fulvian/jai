"""Skill Persistence - Salvataggio skill cristallizzate su disco.

Persiste le skill approvate nel formato SKILL.md compatibile con ClawHub.
"""

from datetime import datetime
from pathlib import Path

import structlog

from me4brain.core.skills.types import Skill

logger = structlog.get_logger(__name__)

# Default path per skill cristallizzate
DEFAULT_SKILLS_DIR = Path.home() / ".me4brain" / "skills" / "crystallized"


def ensure_skills_dir(path: Path | None = None) -> Path:
    """Crea directory skills se non esiste."""
    skills_dir = path or DEFAULT_SKILLS_DIR
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def skill_to_markdown(
    skill: Skill,
    tool_chain: list[str],
    input_query: str,
    risk_level: str = "SAFE",
) -> str:
    """Converte Skill in formato SKILL.md.

    Args:
        skill: Skill da convertire
        tool_chain: Tool utilizzati
        input_query: Query originale
        risk_level: Livello rischio

    Returns:
        Contenuto SKILL.md
    """
    now = datetime.now().isoformat()

    # YAML frontmatter
    frontmatter = f"""---
name: {skill.name}
description: {skill.description}
version: "1.0.0"
type: crystallized
risk_level: {risk_level}
created_at: {now}
confidence: {skill.confidence:.2f}
tool_chain:
{chr(10).join(f"  - {tool}" for tool in tool_chain)}
triggers:
  - "{input_query[:100]}"
---
"""

    # Body con istruzioni
    body = f"""
# {skill.name}

{skill.description}

## Quando Usare

Questa skill viene attivata quando l'utente chiede:
- "{input_query}"

## Tool Chain

Questa skill esegue i seguenti tool in sequenza:

{chr(10).join(f"{i + 1}. `{tool}`" for i, tool in enumerate(tool_chain))}

## Istruzioni

{skill.code if skill.code else "Esegui la sequenza tool chain come definita."}

## Note

- **Generata automaticamente** dal sistema di crystallization
- **Risk Level**: {risk_level}
- **Confidence Score**: {skill.confidence:.2f}
"""

    return frontmatter + body


def persist_skill_to_disk(
    skill: Skill,
    tool_chain: list[str],
    input_query: str,
    risk_level: str = "SAFE",
    skills_dir: Path | None = None,
) -> Path:
    """Salva skill come file SKILL.md.

    Args:
        skill: Skill da salvare
        tool_chain: Tool utilizzati
        input_query: Query originale
        risk_level: Livello rischio
        skills_dir: Directory destinazione (default: ~/.me4brain/skills/crystallized)

    Returns:
        Path del file creato
    """
    # Ensure directory exists
    target_dir = ensure_skills_dir(skills_dir)

    # Create subdirectory for this skill
    skill_dir = target_dir / skill.id
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Generate markdown content
    content = skill_to_markdown(skill, tool_chain, input_query, risk_level)

    # Write file
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")

    logger.info(
        "skill_persisted",
        skill_id=skill.id,
        skill_name=skill.name,
        path=str(skill_file),
    )

    return skill_file


def delete_skill_from_disk(skill_id: str, skills_dir: Path | None = None) -> bool:
    """Elimina skill da disco.

    Args:
        skill_id: ID skill da eliminare
        skills_dir: Directory skills

    Returns:
        True se eliminata
    """
    target_dir = skills_dir or DEFAULT_SKILLS_DIR
    skill_dir = target_dir / skill_id

    if skill_dir.exists():
        import shutil

        shutil.rmtree(skill_dir)
        logger.info("skill_deleted_from_disk", skill_id=skill_id)
        return True

    return False


def list_persisted_skills(skills_dir: Path | None = None) -> list[Path]:
    """Lista tutte le skill persistite.

    Args:
        skills_dir: Directory skills

    Returns:
        Lista path ai file SKILL.md
    """
    target_dir = skills_dir or DEFAULT_SKILLS_DIR

    if not target_dir.exists():
        return []

    return list(target_dir.glob("*/SKILL.md"))
