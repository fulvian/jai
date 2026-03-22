"""Crystallizer - Logica di cristallizzazione automatica delle skill."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime

import structlog

from me4brain.core.skills.registry_deprecated import SkillRegistry
from me4brain.core.skills.types import ExecutionTrace, Skill

logger = structlog.get_logger(__name__)


class Crystallizer:
    """
    Auto-genera skill da tool chain di successo.

    Implementa il pattern Voyager: quando una sequenza di tool
    viene eseguita con successo almeno N volte (o è particolarmente
    interessante), viene "cristallizzata" come skill riutilizzabile.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        embed_func: Callable | None = None,
        llm_func: Callable | None = None,
        min_tools: int = 2,
    ):
        """
        Inizializza il crystallizer.

        Args:
            registry: Registry per salvare skill cristallizzate
            embed_func: Funzione per generare embedding (async)
            llm_func: Funzione per generare descrizioni (async)
            min_tools: Numero minimo di tool per cristallizzare
        """
        self.registry = registry
        self.embed_func = embed_func
        self.llm_func = llm_func
        self.min_tools = min_tools

        # Contatori per trace simili (non ancora cristallizzate)
        self._pending_signatures: dict[str, int] = {}

    async def process_trace(self, trace: ExecutionTrace) -> Skill | None:
        """
        Processa una trace completata e decide se cristallizzare.

        Args:
            trace: Trace di esecuzione completata

        Returns:
            Skill cristallizzata se creata, None altrimenti
        """
        # Condizioni base per cristallizzazione
        if not self._is_crystallizable(trace):
            logger.debug(
                "trace_not_crystallizable",
                session_id=trace.session_id,
                reason="conditions_not_met",
            )
            return None

        signature = trace.signature

        # Cerca skill esistente con stessa signature
        existing = await self.registry.find_by_signature(signature)

        if existing:
            # Rinforza skill esistente
            await self._reinforce_existing(trace, existing)
            return None

        # Nuova potenziale skill: incrementa contatore
        self._pending_signatures[signature] = self._pending_signatures.get(signature, 0) + 1

        # Cristallizza al primo successo (pattern aggressivo)
        # Alternativa: attendere N successi prima di cristallizzare
        skill = await self._crystallize_new(trace)

        if skill:
            # Reset contatore
            self._pending_signatures.pop(signature, None)

        return skill

    def _is_crystallizable(self, trace: ExecutionTrace) -> bool:
        """Verifica se una trace può essere cristallizzata."""
        # Deve avere successo
        if not trace.success:
            return False

        # Deve avere almeno N tool
        if len(trace.tool_chain) < self.min_tools:
            return False

        # Tutti i tool devono avere successo
        if not all(t.success for t in trace.tool_chain):
            return False

        return True

    async def _crystallize_new(self, trace: ExecutionTrace) -> Skill | None:
        """
        Crea una nuova skill da una trace.

        Args:
            trace: Trace da cristallizzare

        Returns:
            Nuova Skill o None se fallisce
        """
        try:
            # Genera nome e descrizione
            name = await self._generate_name(trace)
            description = await self._generate_description(trace)

            # Serializza tool chain come codice
            code = self._serialize_tool_chain(trace)

            # Genera embedding
            embedding = await self._generate_embedding(trace)

            # Crea skill
            skill = Skill(
                id=str(uuid.uuid4())[:16],
                name=name,
                description=description,
                type="crystallized",
                code=code,
                embedding=embedding,
                usage_count=1,
                success_count=1,
                source_trace_id=trace.session_id,
                tool_signature=trace.signature,
                created_at=datetime.now(),
                last_used=datetime.now(),
            )

            # Salva nel registry
            await self.registry.register_crystallized(skill)

            logger.info(
                "skill_crystallized",
                skill_id=skill.id,
                name=name,
                tool_count=len(trace.tool_chain),
                signature=trace.signature,
            )

            return skill

        except Exception as e:
            logger.error(
                "crystallization_failed",
                session_id=trace.session_id,
                error=str(e),
            )
            return None

    async def _reinforce_existing(self, trace: ExecutionTrace, skill: Skill) -> None:
        """
        Rinforza skill esistente con nuovo usage.

        Args:
            trace: Trace di esecuzione
            skill: Skill esistente da rinforzare
        """
        skill.record_usage(success=trace.success)
        await self.registry.update(skill)

        logger.debug(
            "skill_reinforced",
            skill_id=skill.id,
            name=skill.name,
            usage_count=skill.usage_count,
            success_rate=skill.success_rate,
        )

    async def _generate_name(self, trace: ExecutionTrace) -> str:
        """Genera nome per la skill basato sulla tool chain."""
        # Usa LLM se disponibile
        if self.llm_func:
            try:
                prompt = f"""Genera un nome breve (2-4 parole, snake_case) per questa skill:
Query: {trace.input_query}
Tool usati: {", ".join(t.name for t in trace.tool_chain)}
Output: {trace.final_output[:200] if trace.final_output else "N/A"}

Rispondi SOLO con il nome, senza spiegazioni."""

                name = await self.llm_func(prompt)
                return name.strip().lower().replace(" ", "_")[:50]
            except Exception:
                pass

        # Fallback: concatena primi 2 tool
        tool_names = [t.name.split("_")[0] for t in trace.tool_chain[:2]]
        return "_".join(tool_names) + "_chain"

    async def _generate_description(self, trace: ExecutionTrace) -> str:
        """Genera descrizione per la skill."""
        # Usa LLM se disponibile
        if self.llm_func:
            try:
                prompt = f"""Genera una descrizione concisa (1 frase) per questa skill automatica:
Query utente: {trace.input_query}
Tool chain: {" -> ".join(t.name for t in trace.tool_chain)}

Rispondi SOLO con la descrizione."""

                return await self.llm_func(prompt)
            except Exception:
                pass

        # Fallback: descrizione generica
        tools = " → ".join(t.name for t in trace.tool_chain)
        return f"Skill auto-generata: {tools}"

    def _serialize_tool_chain(self, trace: ExecutionTrace) -> str:
        """Serializza tool chain in formato JSON."""
        chain = []
        for tool in trace.tool_chain:
            chain.append(
                {
                    "name": tool.name,
                    "args": tool.args,
                    # Non salviamo il risultato (troppo grande)
                }
            )
        return json.dumps(chain, indent=2, ensure_ascii=False)

    async def _generate_embedding(self, trace: ExecutionTrace) -> list[float]:
        """Genera embedding per la skill."""
        if not self.embed_func:
            return []

        try:
            # Combina query + tool names per embedding
            text = f"{trace.input_query} | {' '.join(t.name for t in trace.tool_chain)}"
            return await self.embed_func(text)
        except Exception as e:
            logger.warning("embedding_generation_failed", error=str(e))
            return []

    @property
    def pending_count(self) -> int:
        """Numero di signature in attesa di cristallizzazione."""
        return len(self._pending_signatures)
