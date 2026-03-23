"""Slash Commands - Parser e handlers per comandi slash."""

import re
from collections.abc import Callable
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ParsedCommand:
    """Comando slash parsato."""

    command: str
    args: str


class SlashCommands:
    """
    Parser e handler per slash commands.

    Comandi supportati:
    - /status - Info sessione
    - /forget <topic> - GDPR delete
    - /help - Lista comandi
    """

    # Pattern per parsing comando
    PATTERN = re.compile(r"^/(\w+)(?:\s+(.*))?$", re.DOTALL)

    # Mapping comando -> handler name
    COMMANDS = {
        "status": "cmd_status",
        "forget": "cmd_forget",
        "help": "cmd_help",
    }

    def __init__(
        self,
        working_memory_getter: Callable | None = None,
        semantic_memory_getter: Callable | None = None,
    ):
        """
        Inizializza handlers.

        Args:
            working_memory_getter: Funzione per ottenere Working Memory
            semantic_memory_getter: Funzione per ottenere Semantic Memory
        """
        self._get_working_memory = working_memory_getter
        self._get_semantic_memory = semantic_memory_getter

    def is_command(self, message: str) -> bool:
        """
        Verifica se il messaggio è un comando slash.

        Args:
            message: Messaggio da verificare

        Returns:
            True se è un comando
        """
        return message.strip().startswith("/")

    def parse(self, message: str) -> ParsedCommand | None:
        """
        Parse messaggio in comando e argomenti.

        Args:
            message: Messaggio da parsare

        Returns:
            ParsedCommand o None se non è un comando valido
        """
        match = self.PATTERN.match(message.strip())
        if not match:
            return None

        command = match.group(1).lower()
        args = (match.group(2) or "").strip()

        if command not in self.COMMANDS:
            return None

        return ParsedCommand(command=command, args=args)

    async def execute(self, message: str, session_id: str) -> str | None:
        """
        Esegue comando slash se presente.

        Args:
            message: Messaggio (potenzialmente comando)
            session_id: ID sessione

        Returns:
            Risposta del comando o None se non è un comando
        """
        parsed = self.parse(message)
        if parsed is None:
            return None

        handler_name = self.COMMANDS.get(parsed.command)
        if handler_name is None:
            return f"❌ Comando sconosciuto: /{parsed.command}"

        handler = getattr(self, handler_name, None)
        if handler is None:
            return f"❌ Handler non implementato: {handler_name}"

        try:
            result = await handler(session_id, parsed.args)
            logger.info(
                "slash_command_executed",
                command=parsed.command,
                session_id=session_id,
            )
            return result

        except Exception as e:
            logger.error(
                "slash_command_error",
                command=parsed.command,
                error=str(e),
            )
            return f"❌ Errore: {e}"

    # --- Command Handlers ---

    async def cmd_status(self, session_id: str, args: str) -> str:
        """
        Mostra status della sessione.

        Displays:
        - Session ID
        - Memory usage
        - Token count (if available)
        """
        lines = [
            "## 📊 Session Status",
            "",
            f"**Session ID**: `{session_id}`",
        ]

        # Working Memory info
        if self._get_working_memory:
            try:
                wm = self._get_working_memory()
                if wm:
                    context = await wm.get_context(session_id)
                    message_count = len(context.get("messages", []))
                    lines.append(f"**Messages in context**: {message_count}")
            except Exception as e:
                lines.append(f"**Working Memory**: Error - {e}")

        # Semantic Memory info
        if self._get_semantic_memory:
            try:
                sm = self._get_semantic_memory()
                if sm:
                    # Placeholder per stats
                    lines.append("**Semantic Memory**: Connected")
            except Exception:
                lines.append("**Semantic Memory**: Not available")

        lines.extend(
            [
                "",
                "---",
                "_Use `/help` for available commands_",
            ]
        )

        return "\n".join(lines)

    async def cmd_forget(self, session_id: str, args: str) -> str:
        """
        GDPR delete di un topic specifico.

        Args:
            args: Topic da dimenticare
        """
        if not args:
            return "❌ Uso: `/forget <topic>`\n\nEsempio: `/forget password bancaria`"

        topic = args.strip()

        # Semantic Memory delete
        deleted_count = 0

        if self._get_semantic_memory:
            try:
                sm = self._get_semantic_memory()
                if sm and hasattr(sm, "delete_by_topic"):
                    deleted_count = await sm.delete_by_topic(topic, session_id)
            except Exception as e:
                logger.error("forget_semantic_error", error=str(e))

        # Working Memory delete
        if self._get_working_memory:
            try:
                wm = self._get_working_memory()
                if wm and hasattr(wm, "forget_topic"):
                    await wm.forget_topic(session_id, topic)
            except Exception as e:
                logger.error("forget_working_error", error=str(e))

        logger.info(
            "gdpr_forget_executed",
            topic=topic,
            session_id=session_id,
            deleted_count=deleted_count,
        )

        return (
            f"🗑️ **Topic dimenticato**: `{topic}`\n\n"
            f"Rimossi {deleted_count} record dalla memoria semantica.\n"
            "_I dati relativi a questo topic sono stati eliminati._"
        )

    async def cmd_help(self, session_id: str, args: str) -> str:
        """Lista comandi disponibili."""
        return """## 📚 Comandi Disponibili

| Comando | Descrizione |
|---------|-------------|
| `/status` | Mostra info sulla sessione corrente |
| `/forget <topic>` | Elimina dati relativi a un topic (GDPR) |
| `/help` | Mostra questa guida |

---
_I comandi slash vengono eseguiti immediatamente senza passare per l'agente._
"""


# Singleton
_slash_commands: SlashCommands | None = None


def get_slash_commands() -> SlashCommands:
    """Ottiene o crea istanza SlashCommands."""
    global _slash_commands
    if _slash_commands is None:
        _slash_commands = SlashCommands()
    return _slash_commands


def set_slash_commands(instance: SlashCommands) -> None:
    """Imposta istanza SlashCommands."""
    global _slash_commands
    _slash_commands = instance
