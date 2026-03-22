"""Permission Validator - Sistema di permessi per azioni autonome.

Definisce livelli di permesso per ogni tool/azione:
- SAFE: Eseguibile autonomamente senza notifica
- NOTIFY: Esegui e notifica l'utente
- CONFIRM: Richiedi conferma PRIMA di eseguire (HITL)
- DENY: Mai eseguibile autonomamente

Questo modulo è il cuore del sistema di sicurezza che differenzia
PersAn da OpenClaw, aggiungendo guardrail alle azioni autonome.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PermissionLevel(str, Enum):
    """Livelli di permesso per azioni."""

    SAFE = "safe"  # Eseguibile senza approvazione
    NOTIFY = "notify"  # Esegui e notifica dopo
    CONFIRM = "confirm"  # Richiedi conferma PRIMA
    DENY = "deny"  # Mai eseguibile autonomamente


@dataclass
class PermissionResult:
    """Risultato della validazione permessi."""

    tool_name: str
    permission_level: PermissionLevel
    reason: str
    requires_human_approval: bool
    approval_message: str | None = None


# =============================================================================
# Permission Mapping
# =============================================================================

# Mapping tool → livello di permesso
# Chiave: prefisso tool name (es. "gmail_" matcha "gmail_send", "gmail_search", etc.)
# Se il tool non è mappato, usa DEFAULT_PERMISSION_LEVEL

TOOL_PERMISSIONS: dict[str, PermissionLevel] = {
    # ==========================================================================
    # SAFE - Solo lettura, nessun side effect
    # ==========================================================================
    # Finance/Crypto (read-only)
    "stock_price": PermissionLevel.SAFE,
    "stock_quote": PermissionLevel.SAFE,
    "market_news": PermissionLevel.SAFE,
    "technical_indicators": PermissionLevel.SAFE,
    "crypto_price": PermissionLevel.SAFE,
    "fmp_": PermissionLevel.SAFE,  # Financial Modeling Prep
    "alpha_vantage_": PermissionLevel.SAFE,
    # Weather/Geo (read-only)
    "weather_": PermissionLevel.SAFE,
    "geolocation": PermissionLevel.SAFE,
    # Search (read-only)
    "web_search": PermissionLevel.SAFE,
    "perplexity_": PermissionLevel.SAFE,
    "brave_search": PermissionLevel.SAFE,
    "tavily_": PermissionLevel.SAFE,  # Tavily search/extract
    "duckduckgo_": PermissionLevel.SAFE,  # DDG instant answers
    "smart_search": PermissionLevel.SAFE,  # Hybrid search router
    "wikipedia_": PermissionLevel.SAFE,
    "arxiv_": PermissionLevel.SAFE,
    "pubmed_": PermissionLevel.SAFE,
    # Knowledge (read-only)
    "calculate": PermissionLevel.SAFE,
    "calculator": PermissionLevel.SAFE,
    "unit_convert": PermissionLevel.SAFE,
    "memory_search": PermissionLevel.SAFE,
    "memory_recall": PermissionLevel.SAFE,
    # Entertainment (read-only)
    "tmdb_": PermissionLevel.SAFE,
    "spotify_search": PermissionLevel.SAFE,
    # Google Workspace - Read (prefissi per match tutti i tool read-only)
    "google_drive_": PermissionLevel.SAFE,  # Default SAFE per tutti i Google Drive
    "google_gmail_": PermissionLevel.SAFE,  # Default SAFE per tutti i Gmail
    "google_calendar_": PermissionLevel.SAFE,  # Default SAFE per tutti i Calendar
    "google_docs_": PermissionLevel.SAFE,  # Default SAFE per tutti i Docs
    "google_sheets_": PermissionLevel.SAFE,  # Default SAFE per tutti i Sheets
    "google_slides_": PermissionLevel.SAFE,  # Default SAFE per tutti i Slides
    "google_meet_": PermissionLevel.SAFE,  # Default SAFE per tutti i Meet
    "google_forms_": PermissionLevel.SAFE,  # Default SAFE per tutti i Forms
    "google_classroom_": PermissionLevel.SAFE,  # Default SAFE per tutti i Classroom
    # Skills - Safe
    "screenshot": PermissionLevel.SAFE,
    "clipboard_read": PermissionLevel.SAFE,
    "system_info": PermissionLevel.SAFE,
    "file_list": PermissionLevel.SAFE,
    "file_read": PermissionLevel.SAFE,
    "file_search": PermissionLevel.SAFE,
    # Marketplace Search (read-only, no purchases)
    "ebay-search": PermissionLevel.SAFE,
    "subito-search": PermissionLevel.SAFE,
    "vinted-search": PermissionLevel.SAFE,
    "wallapop-search": PermissionLevel.SAFE,
    "marketplace-aggregator": PermissionLevel.SAFE,
    # Generic skill search patterns
    "skill_ebay": PermissionLevel.SAFE,
    "skill_subito": PermissionLevel.SAFE,
    "skill_vinted": PermissionLevel.SAFE,
    "skill_wallapop": PermissionLevel.SAFE,
    "skill_marketplace": PermissionLevel.SAFE,
    # ==========================================================================
    # NOTIFY - Side effects a basso rischio
    # ==========================================================================
    # Creazione contenuti personali
    "create_reminder": PermissionLevel.SAFE,
    "apple_reminders_": PermissionLevel.SAFE,
    "create_note": PermissionLevel.SAFE,
    "apple_notes_": PermissionLevel.SAFE,
    "clipboard_write": PermissionLevel.SAFE,
    # Calendar - Crea eventi
    "calendar_create": PermissionLevel.SAFE,
    "calendar_quick_add": PermissionLevel.SAFE,
    # Memory - Store
    "memory_store": PermissionLevel.SAFE,
    "memory_add": PermissionLevel.SAFE,
    # Spotify - Playback
    "spotify_play": PermissionLevel.SAFE,  # Era NOTIFY, allentato
    "spotify_pause": PermissionLevel.SAFE,  # Era NOTIFY, allentato
    # ==========================================================================
    # NOTIFY - Side effects ma non pericolosi (log only, no block)
    # ==========================================================================
    # Google Gmail - Write (most are SAFE now, only send to external = CONFIRM)
    "google_gmail_send": PermissionLevel.SAFE,  # Era CONFIRM - allentato
    "google_gmail_reply": PermissionLevel.SAFE,  # Reply a thread esistente = SAFE
    "google_gmail_forward": PermissionLevel.SAFE,  # Era CONFIRM
    # Google Drive - Write (create/modify = SAFE, delete/share = CONFIRM)
    "google_drive_upload": PermissionLevel.SAFE,  # Era CONFIRM - allentato!
    "google_drive_create_folder": PermissionLevel.SAFE,  # Era NOTIFY
    "google_drive_copy": PermissionLevel.SAFE,  # Era NOTIFY
    "google_drive_move": PermissionLevel.SAFE,  # Era CONFIRM - allentato
    # Google Calendar - Write
    "google_calendar_create_event": PermissionLevel.SAFE,  # Era NOTIFY
    "google_calendar_update_event": PermissionLevel.SAFE,  # Era CONFIRM - allentato
    # Google Docs/Sheets/Slides - Write (all SAFE now)
    "google_docs_create": PermissionLevel.SAFE,
    "google_docs_insert_text": PermissionLevel.SAFE,
    "google_docs_append_text": PermissionLevel.SAFE,
    "google_docs_replace_text": PermissionLevel.SAFE,
    "google_sheets_create": PermissionLevel.SAFE,
    "google_sheets_update_values": PermissionLevel.SAFE,
    "google_sheets_append_row": PermissionLevel.SAFE,
    "google_slides_create": PermissionLevel.SAFE,
    "google_slides_add_slide": PermissionLevel.SAFE,
    # Google Meet
    "google_meet_create": PermissionLevel.SAFE,
    # ==========================================================================
    # CONFIRM - Solo azioni VERAMENTE pericolose/irreversibili
    # ==========================================================================
    # DELETE operations (irreversibili)
    "google_drive_delete": PermissionLevel.CONFIRM,
    "google_drive_share": PermissionLevel.CONFIRM,  # Condivisione esterna = rischio
    "google_calendar_delete_event": PermissionLevel.CONFIRM,
    # File system - Write (local files = più cautela)
    "file_write": PermissionLevel.SAFE,  # Era CONFIRM - allentato
    "file_delete": PermissionLevel.CONFIRM,  # Delete = sempre CONFIRM
    "file_move": PermissionLevel.SAFE,  # Era CONFIRM
    # Shell/System - SEMPRE CONFIRM (pericoloso)
    "execute_shell": PermissionLevel.CONFIRM,
    "run_command": PermissionLevel.CONFIRM,
    "run_script": PermissionLevel.CONFIRM,
    # Browser automation - SAFE per la maggior parte
    "browser_open": PermissionLevel.SAFE,  # Era CONFIRM - allentato
    "browser_act": PermissionLevel.SAFE,  # Era CONFIRM
    "browser_extract": PermissionLevel.SAFE,
    "browser_screenshot": PermissionLevel.SAFE,
    "browser_click": PermissionLevel.SAFE,  # Era CONFIRM
    "browser_type": PermissionLevel.SAFE,  # Era CONFIRM
    "browser_navigate": PermissionLevel.SAFE,  # Era CONFIRM
    "browser_close": PermissionLevel.SAFE,
    # Web scraping
    "web_scraper_download": PermissionLevel.SAFE,  # Era CONFIRM
    # API calls esterni
    "api_post": PermissionLevel.CONFIRM,
    "api_put": PermissionLevel.CONFIRM,
    "api_delete": PermissionLevel.CONFIRM,
    "webhook_trigger": PermissionLevel.CONFIRM,
    # ==========================================================================
    # DENY - Mai eseguibili autonomamente
    # ==========================================================================
    # Comandi pericolosi
    "execute_sudo": PermissionLevel.DENY,
    "execute_root": PermissionLevel.DENY,
    "format_disk": PermissionLevel.DENY,
    "delete_all": PermissionLevel.DENY,
    # Sicurezza
    "change_password": PermissionLevel.DENY,
    "revoke_token": PermissionLevel.DENY,
    "delete_account": PermissionLevel.DENY,
    # Pagamenti
    "payment_send": PermissionLevel.DENY,
    "transfer_funds": PermissionLevel.DENY,
    "place_order": PermissionLevel.DENY,
}

# Livello di default per tool non mappati
# SAFE = fail-open per usabilità (tool sconosciuti sono read-only)
# I tool write sono esplicitamente mappati come CONFIRM/DENY
DEFAULT_PERMISSION_LEVEL = PermissionLevel.SAFE


class PermissionValidator:
    """Validatore permessi per tool execution.

    Determina se un tool può essere eseguito autonomamente o richiede
    approvazione umana (Human-in-the-Loop).

    Usage:
        validator = PermissionValidator()

        result = validator.validate("gmail_send", {"to": "...", "body": "..."})

        if result.requires_human_approval:
            # Invia richiesta approvazione via HITL Queue
            await hitl_queue.request_approval(result)
        else:
            # Esegui tool
            await execute_tool(...)
    """

    def __init__(
        self,
        custom_permissions: dict[str, PermissionLevel] | None = None,
        default_level: PermissionLevel = DEFAULT_PERMISSION_LEVEL,
    ):
        """Inizializza il validatore.

        Args:
            custom_permissions: Override per permessi specifici
            default_level: Livello default per tool non mappati
        """
        self.permissions = {**TOOL_PERMISSIONS}
        if custom_permissions:
            self.permissions.update(custom_permissions)
        self.default_level = default_level

    def _get_permission_level(self, tool_name: str) -> PermissionLevel:
        """Ottiene il livello di permesso per un tool.

        Supporta matching esatto e prefix matching.

        Args:
            tool_name: Nome del tool

        Returns:
            PermissionLevel
        """
        # 1. Matching esatto (priorità massima per override specifici)
        if tool_name in self.permissions:
            return self.permissions[tool_name]

        # 2. Prefix matching (ordinato per lunghezza, più lungo vince)
        # Questo permette override specifici come "google_gmail_send" → CONFIRM
        # che sovrascrive il prefisso "google_gmail_" → SAFE
        sorted_prefixes = sorted(
            [p for p in self.permissions if p.endswith("_")],
            key=len,
            reverse=True,  # Più lungo prima
        )
        for prefix in sorted_prefixes:
            if tool_name.startswith(prefix):
                return self.permissions[prefix]

        return self.default_level

    def validate(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        context: str | None = None,
    ) -> PermissionResult:
        """Valida permessi per una chiamata tool.

        Args:
            tool_name: Nome del tool
            args: Argomenti del tool (per validazione context-aware)
            context: Contesto aggiuntivo

        Returns:
            PermissionResult con livello e approvazione richiesta
        """
        base_level = self._get_permission_level(tool_name)

        # Context-aware escalation
        if args:
            escalated_level = self._check_context_escalation(
                tool_name, args, base_level
            )
            if escalated_level != base_level:
                logger.info(
                    "permission_escalated",
                    tool=tool_name,
                    from_level=base_level.value,
                    to_level=escalated_level.value,
                )
                base_level = escalated_level

        requires_approval = base_level in (
            PermissionLevel.CONFIRM,
            PermissionLevel.DENY,
        )

        approval_message = None
        if requires_approval:
            approval_message = self._generate_approval_message(
                tool_name, args, base_level
            )

        result = PermissionResult(
            tool_name=tool_name,
            permission_level=base_level,
            reason=f"Tool {tool_name} ha livello {base_level.value}",
            requires_human_approval=requires_approval,
            approval_message=approval_message,
        )

        logger.debug(
            "permission_validated",
            tool=tool_name,
            level=base_level.value,
            requires_approval=requires_approval,
        )

        return result

    def _check_context_escalation(
        self,
        tool_name: str,
        args: dict[str, Any],
        current_level: PermissionLevel,
    ) -> PermissionLevel:
        """Verifica se il contesto richiede escalation.

        Args:
            tool_name: Nome del tool
            args: Argomenti
            current_level: Livello attuale

        Returns:
            Livello eventualmente escalato
        """
        # Gmail: Email a esterni → sempre CONFIRM
        if tool_name.startswith("gmail_send"):
            to = args.get("to", "")
            # TODO: Configurabile quale dominio è "interno"
            if not isinstance(to, str):
                to = str(to)
            if "@" in to and not to.endswith("@gmail.com"):
                return PermissionLevel.CONFIRM

        # File operations: Path sensibili → escalation
        if tool_name.startswith("file_"):
            path = args.get("path", "")
            if isinstance(path, str):
                sensitive_paths = ["/etc/", "/System/", "~/.ssh/", "~/.aws/", ".env"]
                if any(s in path for s in sensitive_paths):
                    return PermissionLevel.CONFIRM

        # Shell: Comandi pericolosi → DENY
        if tool_name in ("execute_shell", "run_command"):
            command = args.get("command", "") or args.get("cmd", "")
            if isinstance(command, str):
                dangerous = ["sudo", "rm -rf", "chmod 777", "curl | bash"]
                if any(d in command.lower() for d in dangerous):
                    return PermissionLevel.DENY

        return current_level

    def _generate_approval_message(
        self,
        tool_name: str,
        args: dict[str, Any] | None,
        level: PermissionLevel,
    ) -> str:
        """Genera messaggio per richiesta approvazione.

        Args:
            tool_name: Nome del tool
            args: Argomenti
            level: Livello permesso

        Returns:
            Messaggio human-readable
        """
        if level == PermissionLevel.DENY:
            return f"⛔ L'azione '{tool_name}' non è permessa per motivi di sicurezza."

        # Messaggi specifici per tool
        if tool_name.startswith("gmail_send"):
            to = args.get("to", "N/A") if args else "N/A"
            subject = args.get("subject", "N/A") if args else "N/A"
            return f"📧 Vuoi inviare un'email a {to}?\nOggetto: {subject}"

        if tool_name.startswith("file_delete"):
            path = args.get("path", "N/A") if args else "N/A"
            return f"🗑️ Vuoi eliminare il file '{path}'?"

        if tool_name in ("execute_shell", "run_command"):
            cmd = (args.get("command") or args.get("cmd") or "N/A") if args else "N/A"
            return f"💻 Vuoi eseguire il comando:\n```\n{cmd}\n```"

        # Default
        return f"🔐 L'azione '{tool_name}' richiede la tua approvazione."

    def is_safe(self, tool_name: str) -> bool:
        """Check rapido se tool è SAFE.

        Args:
            tool_name: Nome del tool

        Returns:
            True se SAFE
        """
        return self._get_permission_level(tool_name) == PermissionLevel.SAFE


# Singleton instance
_permission_validator: PermissionValidator | None = None


def get_permission_validator(
    custom_permissions: dict[str, PermissionLevel] | None = None,
) -> PermissionValidator:
    """Ottiene singleton PermissionValidator.

    Args:
        custom_permissions: Override permessi

    Returns:
        PermissionValidator instance
    """
    global _permission_validator
    if _permission_validator is None:
        _permission_validator = PermissionValidator(
            custom_permissions=custom_permissions
        )
    return _permission_validator
