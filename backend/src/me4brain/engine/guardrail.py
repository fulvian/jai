"""LLM Guardrail - Valida input/output per prompt injection e contenuti pericolosi.

Questo modulo implementa guardrail di sicurezza per proteggere il sistema da:
1. Prompt Injection: Tentativi di manipolare il comportamento dell'LLM
2. Comandi Pericolosi: Esecuzione di comandi che possono danneggiare il sistema
3. Data Exfiltration: Tentativi di estrarre dati sensibili

Ispirato a OpenClaw ma con sicurezza migliorata.
"""

import re
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class ThreatLevel(str, Enum):
    """Livello di minaccia rilevato."""

    SAFE = "safe"  # Nessuna minaccia
    SUSPICIOUS = "suspicious"  # Potenzialmente pericoloso, richiede review
    DANGEROUS = "dangerous"  # Bloccare immediatamente


@dataclass
class GuardrailResult:
    """Risultato della validazione guardrail."""

    threat_level: ThreatLevel
    reason: str | None = None
    sanitized_text: str | None = None
    patterns_matched: list[str] | None = None


# =============================================================================
# Pattern Detection
# =============================================================================

# Pattern per prompt injection (tentativi di manipolare l'LLM)
INJECTION_PATTERNS: list[tuple[str, str]] = [
    # Ignore/Override instructions
    (
        r"ignore\s+(previous|all|above|prior|the)\s+instructions?",
        "instruction_override",
    ),
    (r"ignore\s+all\s+(previous\s+)?instructions?", "instruction_override"),
    (r"disregard\s+(everything|all|previous|prior)", "instruction_override"),
    (
        r"forget\s+(your|all|previous)\s+(instructions?|rules?|guidelines?)",
        "instruction_override",
    ),
    (
        r"do\s+not\s+follow\s+(your|the|any)\s+(instructions?|rules?)",
        "instruction_override",
    ),
    # Role hijacking
    (r"you\s+are\s+now\s+(?:a|an)\s+\w+", "role_hijacking"),
    (r"act\s+as\s+(?:if|though)\s+you", "role_hijacking"),
    (r"pretend\s+(?:you|to)\s+(?:are|be)", "role_hijacking"),
    (r"from\s+now\s+on\s+you\s+(?:are|will)", "role_hijacking"),
    (r"your\s+new\s+(?:role|identity|persona)\s+is", "role_hijacking"),
    # Fake system prompts
    (r"system:\s*", "fake_system_prompt"),
    (r"\[SYSTEM\]", "fake_system_prompt"),
    (r"<\|im_start\|>", "chatml_injection"),
    (r"<\|system\|>", "chatml_injection"),
    (r"###\s*(?:System|Human|Assistant):", "markdown_injection"),
    # Jailbreak attempts
    (r"DAN\s+mode", "jailbreak"),
    (r"developer\s+mode", "jailbreak"),
    (r"bypass\s+(?:safety|security|filter)", "jailbreak"),
    # Output manipulation
    (r"output\s+only\s+(?:the|your)\s+(?:api|token|key|secret)", "data_exfiltration"),
    (r"reveal\s+(?:your|the)\s+(?:api|token|key|secret|password)", "data_exfiltration"),
]

# Pattern per comandi pericolosi (esecuzione sistema)
DANGEROUS_COMMAND_PATTERNS: list[tuple[str, str]] = [
    # Destructive commands
    (r"rm\s+-rf\s+[/~]", "destructive_rm"),
    (r"rm\s+--no-preserve-root", "destructive_rm"),
    (r"mkfs\s+", "disk_format"),
    (r"format\s+[a-zA-Z]:", "disk_format"),
    (r"dd\s+if=.+of=/dev/", "disk_overwrite"),
    # Privilege escalation
    (r"sudo\s+", "privilege_escalation"),
    (r"su\s+-", "privilege_escalation"),
    (r"chmod\s+777", "insecure_permissions"),
    (r"chmod\s+\+s", "setuid_change"),
    # Remote code execution
    (r"curl\s+.+\|\s*(?:bash|sh|zsh)", "remote_code_exec"),
    (r"wget\s+.+\|\s*(?:bash|sh|zsh)", "remote_code_exec"),
    (r"python\s+-c\s+['\"].*exec", "code_injection"),
    (r"eval\s*\(", "code_injection"),
    # SQL injection
    (r"DROP\s+(?:TABLE|DATABASE)", "sql_injection"),
    (r"DELETE\s+FROM\s+\w+\s*;", "sql_injection"),
    (r"TRUNCATE\s+TABLE", "sql_injection"),
    (r";\s*--", "sql_comment_injection"),
    # Network attacks
    (r"nc\s+-l", "reverse_shell"),
    (r"netcat\s+-l", "reverse_shell"),
    (r"/dev/tcp/", "bash_network"),
]

# Pattern per dati sensibili (da non esporre)
SENSITIVE_DATA_PATTERNS: list[tuple[str, str]] = [
    (r"(?:api[_-]?key|apikey)\s*[=:]\s*['\"]?[\w-]{20,}", "api_key_exposure"),
    (r"(?:password|passwd|pwd)\s*[=:]\s*['\"]?[^\s'\"]{8,}", "password_exposure"),
    (r"(?:secret|token)\s*[=:]\s*['\"]?[\w-]{20,}", "secret_exposure"),
    (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", "private_key_exposure"),
    (r"(?:sk-|pk_live_|sk_live_)[\w]{20,}", "api_key_exposure"),  # OpenAI, Stripe
]


class GuardrailValidator:
    """Validatore guardrail per input e output LLM.

    Implementa controlli di sicurezza multi-livello:
    1. Input validation: Blocca prompt injection
    2. Output validation: Blocca comandi pericolosi
    3. Sanitization: Rimuove pattern pericolosi

    Usage:
        validator = GuardrailValidator()

        # Valida input utente
        result = validator.validate_input(user_message)
        if result.threat_level == ThreatLevel.DANGEROUS:
            raise SecurityError(result.reason)

        # Valida output LLM
        result = validator.validate_output(llm_response)
        if result.threat_level != ThreatLevel.SAFE:
            logger.warning("Suspicious output", reason=result.reason)
    """

    def __init__(self, strict_mode: bool = False):
        """Inizializza il validatore.

        Args:
            strict_mode: Se True, SUSPICIOUS diventa DANGEROUS
        """
        self.strict_mode = strict_mode
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compila pattern regex per performance."""
        self._injection_patterns = [
            (re.compile(pattern, re.IGNORECASE), name) for pattern, name in INJECTION_PATTERNS
        ]
        self._dangerous_patterns = [
            (re.compile(pattern, re.IGNORECASE), name)
            for pattern, name in DANGEROUS_COMMAND_PATTERNS
        ]
        self._sensitive_patterns = [
            (re.compile(pattern, re.IGNORECASE), name) for pattern, name in SENSITIVE_DATA_PATTERNS
        ]

    def validate_input(self, text: str) -> GuardrailResult:
        """Valida input utente per prompt injection.

        Args:
            text: Testo input da validare

        Returns:
            GuardrailResult con threat level e dettagli
        """
        if not text:
            return GuardrailResult(threat_level=ThreatLevel.SAFE)

        matched_patterns = []

        # Check prompt injection
        for pattern, name in self._injection_patterns:
            if pattern.search(text):
                matched_patterns.append(f"injection:{name}")

        # Check dangerous commands in input
        for pattern, name in self._dangerous_patterns:
            if pattern.search(text):
                matched_patterns.append(f"dangerous:{name}")

        if matched_patterns:
            threat_level = ThreatLevel.DANGEROUS
            reason = f"Detected: {', '.join(matched_patterns)}"

            logger.warning(
                "guardrail_input_blocked",
                patterns=matched_patterns,
                text_preview=text[:100],
            )

            return GuardrailResult(
                threat_level=threat_level,
                reason=reason,
                patterns_matched=matched_patterns,
            )

        return GuardrailResult(threat_level=ThreatLevel.SAFE)

    def validate_output(self, text: str) -> GuardrailResult:
        """Valida output LLM per comandi pericolosi.

        Args:
            text: Testo output da validare

        Returns:
            GuardrailResult con threat level e dettagli
        """
        if not text:
            return GuardrailResult(threat_level=ThreatLevel.SAFE)

        matched_patterns = []

        # Check dangerous commands
        for pattern, name in self._dangerous_patterns:
            if pattern.search(text):
                matched_patterns.append(f"dangerous:{name}")

        # Check sensitive data exposure
        for pattern, name in self._sensitive_patterns:
            if pattern.search(text):
                matched_patterns.append(f"sensitive:{name}")

        if matched_patterns:
            # Dangerous commands = DANGEROUS, sensitive data = SUSPICIOUS
            has_dangerous = any(p.startswith("dangerous:") for p in matched_patterns)
            threat_level = ThreatLevel.DANGEROUS if has_dangerous else ThreatLevel.SUSPICIOUS

            if self.strict_mode and threat_level == ThreatLevel.SUSPICIOUS:
                threat_level = ThreatLevel.DANGEROUS

            reason = f"Output contains: {', '.join(matched_patterns)}"

            logger.warning(
                "guardrail_output_flagged",
                threat_level=threat_level.value,
                patterns=matched_patterns,
            )

            return GuardrailResult(
                threat_level=threat_level,
                reason=reason,
                patterns_matched=matched_patterns,
            )

        return GuardrailResult(threat_level=ThreatLevel.SAFE)

    def sanitize(self, text: str) -> str:
        """Rimuove pattern pericolosi dal testo.

        Args:
            text: Testo da sanitizzare

        Returns:
            Testo sanitizzato con pattern rimossi
        """
        sanitized = text

        # Rimuovi injection patterns
        for pattern, name in self._injection_patterns:
            sanitized = pattern.sub(f"[BLOCKED:{name}]", sanitized)

        return sanitized

    def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
        """Valida argomenti di un tool prima dell'esecuzione.

        Args:
            tool_name: Nome del tool
            args: Argomenti del tool

        Returns:
            GuardrailResult
        """
        # Serializza args per validazione
        args_str = str(args)

        # Valida come output (potrebbe contenere comandi)
        result = self.validate_output(args_str)

        if result.threat_level != ThreatLevel.SAFE:
            logger.warning(
                "guardrail_tool_args_blocked",
                tool=tool_name,
                reason=result.reason,
            )

        return result


# Singleton instance per uso globale
_guardrail: GuardrailValidator | None = None


def get_guardrail(strict_mode: bool = False) -> GuardrailValidator:
    """Ottiene singleton GuardrailValidator.

    Args:
        strict_mode: Se True, modalità strict

    Returns:
        GuardrailValidator instance
    """
    global _guardrail
    if _guardrail is None:
        _guardrail = GuardrailValidator(strict_mode=strict_mode)
    return _guardrail
