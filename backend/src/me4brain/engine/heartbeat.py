"""Heartbeat Loop - Reasoning periodico autonomo con guardrail.

Implementa un loop asincrono che:
1. Si sveglia periodicamente (default: 5 minuti)
2. Raccoglie contesto (calendar, memory, reminders)
3. Chiede all'LLM se c'è qualcosa da fare
4. Notifica l'utente o richiede approvazione per azioni

Ispirato a OpenClaw ma con guardrail di sicurezza.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import structlog

from me4brain.engine.guardrail import GuardrailValidator, ThreatLevel, get_guardrail
from me4brain.engine.permission_validator import (
    PermissionValidator,
    get_permission_validator,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Types
# =============================================================================


class HeartbeatAction:
    """Azione proposta dal heartbeat."""

    def __init__(
        self,
        action_type: str,
        message: str,
        urgency: str = "low",
        requires_approval: bool = False,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
    ):
        self.action_type = action_type
        self.message = message
        self.urgency = urgency  # low, medium, high
        self.requires_approval = requires_approval
        self.tool_name = tool_name
        self.tool_args = tool_args or {}
        self.created_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Serializza azione."""
        return {
            "action_type": self.action_type,
            "message": self.message,
            "urgency": self.urgency,
            "requires_approval": self.requires_approval,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# Heartbeat Loop
# =============================================================================


class HeartbeatLoop:
    """Loop di reasoning periodico come OpenClaw, MA con guardrail.

    Il heartbeat:
    1. Raccoglie contesto da calendar, memory, reminders
    2. Chiede all'LLM se c'è qualcosa di utile da fare
    3. Se si, notifica l'utente o richiede approvazione

    Usage:
        from me4brain.engine.heartbeat import HeartbeatLoop

        async def on_notify(action: HeartbeatAction):
            # Invia notifica via WebSocket/Telegram/etc.
            print(f"Notification: {action.message}")

        async def on_approval_required(action: HeartbeatAction):
            # Invia richiesta approvazione
            print(f"Approval required: {action.message}")

        engine = await ToolCallingEngine.create()
        heartbeat = HeartbeatLoop(
            engine=engine,
            on_notify=on_notify,
            on_approval_required=on_approval_required,
        )

        await heartbeat.start()
    """

    def __init__(
        self,
        engine: Any,  # ToolCallingEngine
        interval_seconds: int = 300,  # 5 minuti
        on_notify: Callable[[HeartbeatAction], Awaitable[None]] | None = None,
        on_approval_required: Callable[[HeartbeatAction], Awaitable[None]] | None = None,
        guardrail: GuardrailValidator | None = None,
        permission_validator: PermissionValidator | None = None,
    ):
        """Inizializza heartbeat loop.

        Args:
            engine: ToolCallingEngine per eseguire query
            interval_seconds: Intervallo tra heartbeat (default: 5 min)
            on_notify: Callback per notifiche
            on_approval_required: Callback per richieste approvazione
            guardrail: GuardrailValidator (usa default se None)
            permission_validator: PermissionValidator (usa default se None)
        """
        self.engine = engine
        self.interval = interval_seconds
        self.on_notify = on_notify
        self.on_approval_required = on_approval_required
        self.guardrail = guardrail or get_guardrail()
        self.permissions = permission_validator or get_permission_validator()

        self._running = False
        self._task: asyncio.Task | None = None
        self._beat_count = 0

    @property
    def is_running(self) -> bool:
        """Check se loop è attivo."""
        return self._running

    async def start(self) -> None:
        """Avvia il heartbeat loop.

        Non blocca: crea un task in background.
        """
        if self._running:
            logger.warning("heartbeat_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())

        logger.info(
            "🫀 heartbeat_loop_started",
            interval_seconds=self.interval,
        )

    async def stop(self) -> None:
        """Ferma il heartbeat loop."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info(
            "🫀 heartbeat_loop_stopped",
            total_beats=self._beat_count,
        )

    async def _loop(self) -> None:
        """Loop principale."""
        while self._running:
            try:
                await self._beat()
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))

            # Aspetta intervallo
            await asyncio.sleep(self.interval)

    async def _beat(self) -> None:
        """Singola iterazione del heartbeat."""
        self._beat_count += 1

        logger.debug(
            "🫀 heartbeat_tick",
            beat_number=self._beat_count,
        )

        # 1. Raccogli contesto
        context = await self._gather_context()

        # 2. Costruisci prompt per LLM
        prompt = self._build_reasoning_prompt(context)

        # 3. Valida input con guardrail
        guardrail_result = self.guardrail.validate_input(prompt)
        if guardrail_result.threat_level == ThreatLevel.DANGEROUS:
            logger.warning(
                "heartbeat_prompt_blocked",
                reason=guardrail_result.reason,
            )
            return

        # 4. Chiedi all'LLM
        try:
            response = await self.engine.run(prompt)
            answer = response.answer
        except Exception as e:
            logger.error("heartbeat_llm_error", error=str(e))
            return

        # 5. Valida output con guardrail
        output_result = self.guardrail.validate_output(answer)
        if output_result.threat_level == ThreatLevel.DANGEROUS:
            logger.warning(
                "heartbeat_output_blocked",
                reason=output_result.reason,
            )
            return

        # 6. Parsa risposta e decidi azione
        action = self._parse_response(answer)

        if action is None or action.action_type == "none":
            logger.debug("heartbeat_no_action_needed")
            return

        # 7. Se c'è un tool, verifica permessi
        if action.tool_name:
            perm_result = self.permissions.validate(
                action.tool_name,
                action.tool_args,
            )
            action.requires_approval = perm_result.requires_human_approval

        # 8. Notifica o richiedi approvazione
        if action.requires_approval:
            if self.on_approval_required:
                await self.on_approval_required(action)
                logger.info(
                    "heartbeat_approval_requested",
                    action=action.action_type,
                    tool=action.tool_name,
                )
        else:
            if self.on_notify:
                await self.on_notify(action)
                logger.info(
                    "heartbeat_notification_sent",
                    action=action.action_type,
                    urgency=action.urgency,
                )

    async def _gather_context(self) -> dict[str, Any]:
        """Raccoglie contesto da varie fonti.

        Returns:
            Dictionary con contesto raccolto
        """
        context: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "calendar": None,
            "memory": None,
            "reminders": None,
        }

        # Calendar - prossimi eventi
        try:
            cal_response = await self.engine.run(
                "Lista i prossimi 3 eventi del calendario di oggi",
                max_tools=2,
            )
            if cal_response.tool_results:
                context["calendar"] = cal_response.answer[:500]
        except Exception as e:
            logger.debug("heartbeat_calendar_error", error=str(e))

        # Memory - discussioni recenti
        try:
            mem_response = await self.engine.run(
                "Cosa abbiamo discusso di recente? Riassumi brevemente.",
                max_tools=2,
            )
            if mem_response.answer:
                context["memory"] = mem_response.answer[:500]
        except Exception as e:
            logger.debug("heartbeat_memory_error", error=str(e))

        return context

    def _build_reasoning_prompt(self, context: dict[str, Any]) -> str:
        """Costruisce prompt per reasoning.

        Args:
            context: Contesto raccolto

        Returns:
            Prompt per LLM
        """
        now = datetime.now()
        time_str = now.strftime("%H:%M del %d/%m/%Y")

        parts = [f"È il {time_str}.", ""]

        if context.get("calendar"):
            parts.append(f"📅 **Calendario**: {context['calendar']}")
            parts.append("")

        if context.get("memory"):
            parts.append(f"🧠 **Recente**: {context['memory']}")
            parts.append("")

        parts.append("""
Sei l'assistente personale dell'utente. Valuta se c'è qualcosa di utile da fare proattivamente.

Considera:
- Eventi imminenti che richiedono preparazione
- Follow-up su discussioni precedenti
- Promemoria o task in sospeso
- Informazioni utili da condividere

Rispondi in JSON:
- Se NON c'è nulla di rilevante: {"action": "none"}
- Se c'è qualcosa da comunicare:
  {
    "action": "notify",
    "message": "Il tuo messaggio per l'utente",
    "urgency": "low|medium|high"
  }
- Se serve un'azione:
  {
    "action": "execute",
    "message": "Descrizione dell'azione",
    "tool_name": "nome_tool",
    "tool_args": {"arg": "value"},
    "requires_approval": true
  }

Rispondi SOLO se c'è qualcosa di veramente utile.
""")

        return "\n".join(parts)

    def _parse_response(self, response: str) -> HeartbeatAction | None:
        """Parsa risposta LLM in azione.

        Args:
            response: Risposta LLM

        Returns:
            HeartbeatAction o None
        """
        import json

        # Cerca JSON nella risposta
        try:
            # Trova blocco JSON
            start = response.find("{")
            end = response.rfind("}") + 1

            if start == -1 or end == 0:
                return None

            json_str = response[start:end]
            data = json.loads(json_str)

            action_type = data.get("action", "none")

            if action_type == "none":
                return None

            return HeartbeatAction(
                action_type=action_type,
                message=data.get("message", ""),
                urgency=data.get("urgency", "low"),
                requires_approval=data.get("requires_approval", False),
                tool_name=data.get("tool_name"),
                tool_args=data.get("tool_args"),
            )

        except json.JSONDecodeError:
            logger.debug("heartbeat_json_parse_error", response=response[:200])
            return None

    async def trigger_manual(self) -> HeartbeatAction | None:
        """Trigger manuale di un heartbeat.

        Utile per testing o per forzare una valutazione.

        Returns:
            Azione risultante o None
        """
        await self._beat()
        return None  # L'azione viene gestita via callback


# =============================================================================
# Singleton
# =============================================================================

_heartbeat: HeartbeatLoop | None = None


async def get_heartbeat(
    engine: Any | None = None,
    interval_seconds: int = 300,
) -> HeartbeatLoop:
    """Ottiene o crea HeartbeatLoop singleton.

    Args:
        engine: ToolCallingEngine (richiesto se singleton non esiste)
        interval_seconds: Intervallo

    Returns:
        HeartbeatLoop instance
    """
    global _heartbeat

    if _heartbeat is None:
        if engine is None:
            raise ValueError("Engine required to create HeartbeatLoop")
        _heartbeat = HeartbeatLoop(engine, interval_seconds)

    return _heartbeat
