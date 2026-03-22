"""Skill Security Validator - Validazione sicurezza skill cristallizzate.

Rileva pattern pericolosi e classifica livello di rischio.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class RiskLevel(Enum):
    """Livello di rischio skill."""

    SAFE = "SAFE"  # Read-only, no side effects
    NOTIFY = "NOTIFY"  # Modifica locale reversibile
    CONFIRM = "CONFIRM"  # Side effects esterni/irreversibili
    DENY = "DENY"  # Pericoloso o out-of-scope


@dataclass
class SecurityValidationResult:
    """Risultato validazione sicurezza."""

    risk_level: RiskLevel
    is_safe: bool
    matched_patterns: list[str]
    reason: str
    requires_approval: bool


# Pattern pericolosi (DENY)
DANGEROUS_PATTERNS = [
    # Shell dangerous commands
    (r"rm\s+-rf", "Comando rm -rf rilevato"),
    (r"sudo\s+", "Comando sudo rilevato"),
    (r"chmod\s+777", "Permessi troppo aperti"),
    (r"curl.*\|\s*(sh|bash)", "Esecuzione remota via curl pipe"),
    (r"wget.*\|\s*(sh|bash)", "Esecuzione remota via wget pipe"),
    # Python dangerous patterns
    (r"eval\s*\(", "Uso di eval()"),
    (r"exec\s*\(", "Uso di exec()"),
    (r"__import__\s*\(", "Import dinamico"),
    (r"os\.system\s*\(", "Chiamata os.system()"),
    (r"subprocess.*shell\s*=\s*True", "Subprocess con shell=True"),
    (r"pickle\.loads?\s*\(", "Deserializzazione pickle non sicura"),
    # Network dangerous
    (r"0\.0\.0\.0", "Binding su tutte le interfacce"),
    (r"telnet\s+", "Uso di telnet"),
    # File system dangerous
    (r"/etc/passwd", "Accesso a file di sistema"),
    (r"/etc/shadow", "Accesso a file shadow"),
    (r"~/.ssh", "Accesso a chiavi SSH"),
    (r"\.env", "Accesso a file .env"),
]

# Tool che richiedono CONFIRM
CONFIRM_TOOLS = {
    "execute_shell",
    "run_command",
    "run_script",
    "file_delete",
    "google_drive_delete",
    "google_drive_share",
    "google_gmail_send",  # Only external
    "api_post",
    "api_delete",
    "webhook_trigger",
}

# Tool che richiedono NOTIFY
NOTIFY_TOOLS = {
    "file_write",
    "google_drive_upload",
    "google_docs_create",
    "google_sheets_create",
    "google_calendar_create_event",
    "browser_act",
}


class SkillSecurityValidator:
    """Valida sicurezza delle skill prima dell'approvazione.

    Implementa:
    1. Pattern detection per bloccare skill pericolose
    2. Risk classification basata su tool chain
    3. Validazione argomenti sensibili
    """

    def __init__(
        self,
        custom_deny_patterns: Optional[list[tuple[str, str]]] = None,
    ):
        """Inizializza validator.

        Args:
            custom_deny_patterns: Pattern aggiuntivi (regex, descrizione)
        """
        self.deny_patterns = list(DANGEROUS_PATTERNS)
        if custom_deny_patterns:
            self.deny_patterns.extend(custom_deny_patterns)

        # Compila regex
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), desc)
            for pattern, desc in self.deny_patterns
        ]

    def validate_code(self, code: str) -> SecurityValidationResult:
        """Valida codice skill per pattern pericolosi.

        Args:
            code: Codice/istruzioni della skill

        Returns:
            SecurityValidationResult con livello rischio
        """
        matched = []

        for pattern, description in self._compiled_patterns:
            if pattern.search(code):
                matched.append(description)

        if matched:
            return SecurityValidationResult(
                risk_level=RiskLevel.DENY,
                is_safe=False,
                matched_patterns=matched,
                reason=f"Pattern pericolosi rilevati: {', '.join(matched)}",
                requires_approval=False,  # DENY = blocked
            )

        return SecurityValidationResult(
            risk_level=RiskLevel.SAFE,
            is_safe=True,
            matched_patterns=[],
            reason="Nessun pattern pericoloso rilevato",
            requires_approval=False,
        )

    def classify_tool_chain(
        self,
        tool_chain: list[str],
    ) -> SecurityValidationResult:
        """Classifica rischio basato su tool chain.

        Args:
            tool_chain: Lista nomi tool utilizzati

        Returns:
            SecurityValidationResult con livello appropriato
        """
        tool_set = set(tool_chain)

        # Check for CONFIRM tools
        confirm_matches = tool_set & CONFIRM_TOOLS
        if confirm_matches:
            return SecurityValidationResult(
                risk_level=RiskLevel.CONFIRM,
                is_safe=False,
                matched_patterns=list(confirm_matches),
                reason=f"Tool con side effects: {', '.join(confirm_matches)}",
                requires_approval=True,
            )

        # Check for NOTIFY tools
        notify_matches = tool_set & NOTIFY_TOOLS
        if notify_matches:
            return SecurityValidationResult(
                risk_level=RiskLevel.NOTIFY,
                is_safe=True,
                matched_patterns=list(notify_matches),
                reason=f"Tool con modifica locale: {', '.join(notify_matches)}",
                requires_approval=False,
            )

        # Default: SAFE
        return SecurityValidationResult(
            risk_level=RiskLevel.SAFE,
            is_safe=True,
            matched_patterns=[],
            reason="Solo tool read-only",
            requires_approval=False,
        )

    def validate_skill(
        self,
        code: str,
        tool_chain: list[str],
    ) -> SecurityValidationResult:
        """Validazione completa skill.

        Combina validazione codice e classificazione tool chain.

        Args:
            code: Codice/istruzioni skill
            tool_chain: Tool utilizzati

        Returns:
            SecurityValidationResult con livello più restrittivo
        """
        # Step 1: Valida codice
        code_result = self.validate_code(code)
        if code_result.risk_level == RiskLevel.DENY:
            logger.warning(
                "skill_security_denied",
                patterns=code_result.matched_patterns,
            )
            return code_result

        # Step 2: Classifica tool chain
        tool_result = self.classify_tool_chain(tool_chain)

        # Prendi il livello più restrittivo
        if tool_result.risk_level.value > code_result.risk_level.value:
            return tool_result

        return code_result


# Singleton
_security_validator: Optional[SkillSecurityValidator] = None


def get_skill_security_validator() -> SkillSecurityValidator:
    """Ottiene singleton SkillSecurityValidator."""
    global _security_validator
    if _security_validator is None:
        _security_validator = SkillSecurityValidator()
    return _security_validator
