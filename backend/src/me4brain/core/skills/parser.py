"""Skill Parser - Parser per file SKILL.md con YAML frontmatter."""

import re
from pathlib import Path
from typing import Optional

import structlog
import yaml
from pydantic import ValidationError

from me4brain.core.skills.types import SkillDefinition

logger = structlog.get_logger(__name__)


class SkillParseError(Exception):
    """Errore durante il parsing di una skill."""

    pass


class SkillParser:
    """Parser per skill esplicite in formato Markdown + YAML frontmatter."""

    # Pattern per estrarre frontmatter YAML (tra ---...---)
    FRONTMATTER_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)$",
        re.DOTALL | re.MULTILINE,
    )

    def parse_file(self, path: Path) -> SkillDefinition:
        """
        Estrae metadati e istruzioni da file SKILL.md.

        Args:
            path: Percorso al file SKILL.md

        Returns:
            SkillDefinition con metadati e istruzioni

        Raises:
            SkillParseError: Se il file non è valido
        """
        if not path.exists():
            raise SkillParseError(f"File non trovato: {path}")

        if not path.suffix.lower() == ".md":
            raise SkillParseError(f"Estensione non valida (atteso .md): {path}")

        content = path.read_text(encoding="utf-8")
        return self.parse_content(content, source_path=str(path))

    def parse_content(
        self, content: str, source_path: Optional[str] = None
    ) -> SkillDefinition:
        """
        Parse contenuto markdown con frontmatter.

        Args:
            content: Contenuto del file markdown
            source_path: Path sorgente per logging

        Returns:
            SkillDefinition parsata
        """
        match = self.FRONTMATTER_PATTERN.match(content.strip())

        if not match:
            raise SkillParseError(
                f"Frontmatter YAML non trovato in {source_path or 'contenuto'}"
            )

        yaml_str = match.group(1)
        markdown_body = match.group(2).strip()

        try:
            metadata = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            raise SkillParseError(f"YAML non valido: {e}") from e

        if not isinstance(metadata, dict):
            raise SkillParseError("Il frontmatter deve essere un dizionario YAML")

        # Validazione campi obbligatori
        if "name" not in metadata:
            raise SkillParseError("Campo 'name' obbligatorio nel frontmatter")
        if "description" not in metadata:
            raise SkillParseError("Campo 'description' obbligatorio nel frontmatter")

        # Aggiungi istruzioni dal body markdown
        metadata["instructions"] = markdown_body

        return self.validate_schema(metadata)

    def validate_schema(self, data: dict) -> SkillDefinition:
        """
        Valida lo schema skill contro Pydantic model.

        Args:
            data: Dizionario con dati skill

        Returns:
            SkillDefinition validata

        Raises:
            SkillParseError: Se la validazione fallisce
        """
        try:
            return SkillDefinition(**data)
        except ValidationError as e:
            errors = "; ".join([f"{err['loc']}: {err['msg']}" for err in e.errors()])
            raise SkillParseError(f"Schema non valido: {errors}") from e

    def discover_skills(self, directory: Path) -> list[SkillDefinition]:
        """
        Scopre tutte le skill in una directory.

        Args:
            directory: Directory da scansionare

        Returns:
            Lista di SkillDefinition trovate
        """
        skills: list[SkillDefinition] = []

        if not directory.exists():
            logger.warning("skill_directory_not_found", path=str(directory))
            return skills

        # Cerca file SKILL.md nella directory e sottodirectory
        for skill_file in directory.rglob("SKILL.md"):
            try:
                skill = self.parse_file(skill_file)
                skills.append(skill)
                logger.info(
                    "skill_discovered",
                    name=skill.name,
                    path=str(skill_file),
                )
            except SkillParseError as e:
                logger.error(
                    "skill_parse_error",
                    path=str(skill_file),
                    error=str(e),
                )

        return skills


# Esempio di file SKILL.md valido:
"""
---
name: weather_calendar_sync
description: Sincronizza il meteo con il calendario Google
version: "1.0"
author: Fulvio
tags:
  - weather
  - calendar
  - automation
triggers:
  - "meteo.*calendario"
  - "aggiungi meteo"
tools_required:
  - geo_weather
  - google_calendar_create_event
---

## Istruzioni

1. Ottieni il meteo per la città specificata usando `geo_weather`
2. Crea un evento nel calendario con il riepilogo meteo
3. Imposta la data dell'evento come specificato dall'utente

## Note

Questa skill richiede l'autenticazione Google Calendar attiva.
"""
