"""Skill Extractor - Generalizzazione e ottimizzazione skill da recording."""

from __future__ import annotations

import re
import uuid

import structlog

from me4brain.core.browser.types import (
    ActionType,
    BrowserAction,
    BrowserSkill,
    RecordingState,
)

logger = structlog.get_logger(__name__)


class SkillExtractor:
    """
    Extractor per analizzare e ottimizzare skill.

    Responsabilità:
    - Generalizzazione selectors (CSS → semantic)
    - Identificazione pattern ripetibili
    - Creazione parametri variabili
    - Rimozione azioni ridondanti
    - Validation via replay test
    """

    # Pattern per identificare elementi variabili
    ID_PATTERNS = [
        r"\b[a-f0-9]{8,}\b",  # UUID-like
        r"\b\d{6,}\b",  # Long numbers
        r"(?<=[-_])\d+(?=[-_]|$)",  # Numeric suffixes
    ]

    def __init__(self):
        """Inizializza extractor."""
        self._cache: dict[str, BrowserSkill] = {}

    def analyze(self, recording: RecordingState) -> dict:
        """
        Analizza recording per pattern e ottimizzazioni.

        Args:
            recording: Recording da analizzare

        Returns:
            Dict con analisi
        """
        analysis = {
            "recording_id": recording.id,
            "total_actions": len(recording.actions),
            "action_types": {},
            "potential_parameters": [],
            "redundant_actions": [],
            "optimization_suggestions": [],
        }

        # Conta tipi azione
        for action in recording.actions:
            atype = action.type.value
            analysis["action_types"][atype] = analysis["action_types"].get(atype, 0) + 1

        # Identifica parametri potenziali
        analysis["potential_parameters"] = self._find_parameters(recording.actions)

        # Trova azioni ridondanti
        analysis["redundant_actions"] = self._find_redundant(recording.actions)

        # Suggerimenti ottimizzazione
        analysis["optimization_suggestions"] = self._generate_suggestions(recording, analysis)

        return analysis

    def extract_skill(
        self,
        recording: RecordingState,
        name: str | None = None,
        optimize: bool = True,
    ) -> BrowserSkill:
        """
        Estrae skill ottimizzata da recording.

        Args:
            recording: Recording sorgente
            name: Nome skill
            optimize: Applica ottimizzazioni

        Returns:
            Skill estratta
        """
        actions = recording.actions.copy()

        if optimize:
            # Rimuovi azioni ridondanti
            actions = self._remove_redundant(actions)

            # Generalizza selectors
            actions = self._generalize_selectors(actions)

        # Estrai parametri
        parameters = self._extract_parameters(actions)

        # Genera nome intelligente
        skill_name = name or self._generate_name(recording, actions)

        # Genera descrizione
        description = self._generate_description(actions)

        skill = BrowserSkill(
            id=str(uuid.uuid4())[:12],
            name=skill_name,
            description=description,
            actions=actions,
            parameters=parameters,
            recording_id=recording.id,
            source_url=self._find_source_url(actions),
        )

        logger.info(
            "skill_extracted",
            skill_id=skill.id,
            name=skill.name,
            original_actions=len(recording.actions),
            optimized_actions=len(actions),
        )

        return skill

    def _find_parameters(self, actions: list[BrowserAction]) -> list[dict]:
        """Trova valori che potrebbero essere parametri."""
        params = []

        for i, action in enumerate(actions):
            # URL con variabili
            if action.type == ActionType.NAVIGATE and action.target:
                for pattern in self.ID_PATTERNS:
                    if re.search(pattern, action.target):
                        params.append(
                            {
                                "action_index": i,
                                "type": "url_variable",
                                "pattern": pattern,
                                "value": action.target,
                            }
                        )

            # Valori input
            if action.type == ActionType.TYPE and action.value:
                params.append(
                    {
                        "action_index": i,
                        "type": "input_value",
                        "value": action.value,
                    }
                )

        return params

    def _find_redundant(self, actions: list[BrowserAction]) -> list[int]:
        """Trova azioni ridondanti."""
        redundant = []

        for i, action in enumerate(actions):
            # Navigazioni consecutive alla stessa URL
            if action.type == ActionType.NAVIGATE and i > 0:
                prev = actions[i - 1]
                if prev.type == ActionType.NAVIGATE and prev.target == action.target:
                    redundant.append(i)

            # Screenshot multipli consecutivi
            if action.type == ActionType.SCREENSHOT and i > 0:
                prev = actions[i - 1]
                if prev.type == ActionType.SCREENSHOT:
                    redundant.append(i)

        return redundant

    def _remove_redundant(self, actions: list[BrowserAction]) -> list[BrowserAction]:
        """Rimuove azioni ridondanti."""
        redundant_indices = set(self._find_redundant(actions))
        return [a for i, a in enumerate(actions) if i not in redundant_indices]

    def _generalize_selectors(self, actions: list[BrowserAction]) -> list[BrowserAction]:
        """Generalizza selectors per robustezza."""
        generalized = []

        for action in actions:
            new_action = action.model_copy()

            # Se c'è instruction NL, preferiscila al selector
            if action.instruction and not action.target:
                new_action.target = None  # Usa instruction

            # Generalizza selectors con ID dinamici
            if action.target:
                for pattern in self.ID_PATTERNS:
                    new_action.target = re.sub(
                        pattern,
                        "{dynamic_id}",
                        new_action.target,
                    )

            generalized.append(new_action)

        return generalized

    def _extract_parameters(self, actions: list[BrowserAction]) -> list[dict]:
        """Estrae definizioni parametri."""
        params = []
        seen_types = set()

        for action in actions:
            # URL parameter
            if action.type == ActionType.NAVIGATE and "{dynamic_id}" in (action.target or ""):
                if "url" not in seen_types:
                    params.append(
                        {
                            "name": "url",
                            "type": "string",
                            "description": "Target URL",
                            "required": True,
                        }
                    )
                    seen_types.add("url")

            # Input parameters
            if action.type == ActionType.TYPE and action.value:
                param_name = f"input_{len([p for p in params if 'input_' in p['name']])}"
                params.append(
                    {
                        "name": param_name,
                        "type": "string",
                        "description": "Input value for action",
                        "required": False,
                        "default": action.value,
                    }
                )

        return params

    def _generate_name(
        self,
        recording: RecordingState,
        actions: list[BrowserAction],
    ) -> str:
        """Genera nome skill intelligente."""
        if recording.name:
            return recording.name

        # Usa prima URL come base
        source_url = self._find_source_url(actions)
        if source_url:
            # Estrai dominio
            from urllib.parse import urlparse

            domain = urlparse(source_url).netloc.replace("www.", "")
            return f"skill_{domain.split('.')[0]}_{len(actions)}steps"

        return f"skill_{recording.id}"

    def _generate_description(self, actions: list[BrowserAction]) -> str:
        """Genera descrizione skill."""
        if not actions:
            return "Empty skill"

        # Riassumi azioni
        action_summary = []
        for action in actions[:5]:
            if action.instruction:
                action_summary.append(action.instruction[:30])
            else:
                action_summary.append(f"{action.type.value}")

        desc = f"Automated workflow with {len(actions)} steps: "
        desc += ", ".join(action_summary)

        if len(actions) > 5:
            desc += f", and {len(actions) - 5} more..."

        return desc

    def _find_source_url(self, actions: list[BrowserAction]) -> str | None:
        """Trova URL sorgente."""
        for action in actions:
            if action.type == ActionType.NAVIGATE and action.target:
                return action.target
        return None

    def _generate_suggestions(
        self,
        recording: RecordingState,
        analysis: dict,
    ) -> list[str]:
        """Genera suggerimenti ottimizzazione."""
        suggestions = []

        # Troppe screenshot
        screenshots = analysis["action_types"].get("screenshot", 0)
        if screenshots > 3:
            suggestions.append(f"Consider reducing {screenshots} screenshots to key points only")

        # Molti wait
        waits = analysis["action_types"].get("wait", 0)
        if waits > 2:
            suggestions.append("Multiple explicit waits detected - consider using auto-wait")

        # Azioni ridondanti
        if analysis["redundant_actions"]:
            suggestions.append(
                f"{len(analysis['redundant_actions'])} redundant actions can be removed"
            )

        # Molti parametri
        if len(analysis["potential_parameters"]) > 5:
            suggestions.append("Many variable values detected - consider parameterizing for reuse")

        return suggestions
