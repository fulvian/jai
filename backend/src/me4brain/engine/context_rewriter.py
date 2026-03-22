"""Context-Aware Query Rewriter.

Riscrive le domande follow-up degli utenti in query self-contained,
integrando il contesto conversazionale dalla Working Memory.

Questo modulo risolve il problema critico dove query come "voglio link reali"
perdono il contesto originale (es. "Mac Studio usato 64GB RAM") durante
il routing e la decomposizione.

Design:
- Heuristic-first: controlla se il rewriting è necessario (bypass per query esplicite)
- LLM rewriting: usa Mistral Large per riscrivere con contesto
- Entity-aware: integra entità dal grafo di sessione NetworkX
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from me4brain.llm.nanogpt import NanoGPTClient

logger = structlog.get_logger(__name__)

# Modello per il rewriting (Mistral 3 Large, come da direttiva utente)
REWRITER_MODEL = "mistralai/mistral-large-3-675b-instruct-2512"

# ---------------------------------------------------------------------------
# Prompt per il rewriting conversazionale
# ---------------------------------------------------------------------------
REWRITE_SYSTEM_PROMPT = """\
Sei un Query Rewriter per un sistema di assistente personale multi-tool.

Il tuo compito è riscrivere la NUOVA DOMANDA dell'utente rendendola \
COMPLETAMENTE AUTOCONTENUTA, incorporando il contesto della conversazione.

## REGOLE CRITICHE:
1. La query riscritta DEVE essere comprensibile SENZA la conversazione precedente
2. Includi entità, filtri, vincoli e parametri menzionati nei turni precedenti
3. NON aggiungere informazioni che non sono nella conversazione
4. NON rispondere alla domanda — riscrivi solo la query
5. Mantieni il tono e l'intento dell'utente
6. Se la domanda è già self-contained, restituiscila invariata
7. Rispondi SOLO con la query riscritta, nient'altro

## ESEMPI:

### Esempio 1 — Pronome anaforico
Conversazione:
Utente: Cerco un Mac Studio usato con almeno 64GB di RAM sotto 2500€
Assistente: [risposta con annunci]
Nuova domanda: Tutti i link sono falsi. Voglio link reali.

→ Cerca annunci reali con link funzionanti di Mac Studio usato con almeno 64GB di RAM sotto 2500 euro su marketplace come Subito.it ed eBay.it

### Esempio 2 — Riferimento implicito
Conversazione:
Utente: Che tempo fa a Roma domani?
Assistente: [previsioni Roma]
Nuova domanda: E a Milano?

→ Che tempo fa a Milano domani?

### Esempio 3 — Specializzazione/raffinamento
Conversazione:
Utente: Cerca voli per Londra per il 15 marzo
Assistente: [risultati voli]
Nuova domanda: Solo diretti sotto i 200 euro

→ Cerca voli diretti per Londra il 15 marzo sotto i 200 euro

### Esempio 4 — Feedback negativo
Conversazione:
Utente: Cercami le ultime notizie su Tesla
Assistente: [notizie]
Nuova domanda: No, intendevo Tesla l'auto elettrica, non la società

→ Cercami le ultime notizie sulle auto elettriche Tesla (veicoli), non sulla società finanziaria

### Esempio 5 — Già self-contained
Conversazione:
Utente: Qual è il prezzo del Bitcoin?
Assistente: [prezzo]
Nuova domanda: Che tempo fa a Roma?

→ Che tempo fa a Roma?
"""


@dataclass
class RewriteResult:
    """Risultato del rewriting."""

    original_query: str
    rewritten_query: str
    was_rewritten: bool
    reason: str = ""
    session_entities: list[str] = field(default_factory=list)


class ContextAwareRewriter:
    """Riscrive query follow-up integrando il contesto conversazionale.

    Flusso:
    1. Heuristic check: se la query è già self-contained, skip
    2. Costruisce prompt con cronologia conversazione
    3. LLM riscrive in query autocontenuta
    4. La query riscritta viene usata per routing e decomposizione
    """

    # Soglie per heuristic decision
    MIN_HISTORY_TURNS = 1  # Serve almeno 1 turno precedente
    MAX_HISTORY_TURNS = 6  # Massimo turni per il prompt di rewriting
    MAX_CONTENT_PER_TURN = 500  # Caratteri max per turno nel prompt

    # Pattern che indicano una query che POTREBBE aver bisogno di rewriting
    _FOLLOW_UP_INDICATORS = [
        # Pronomi anaforici italiani
        r"\b(quel(?:lo|la|li|le|i))\b",
        r"\b(quest[oaie])\b",
        r"\b(lo stesso|la stessa|gli stessi|le stesse)\b",
        r"\b(lui|lei|loro|esso|essa)\b",
        r"\b(così|anche|pure)\b",
        # Riferimenti impliciti
        r"\b(il primo|il secondo|l'ultimo|l'altra|gli altri)\b",
        r"\b(cambia|modifica|correggi|aggiorna|rifai|ripeti)\b",
        r"\b(continua|prosegui|vai avanti|approfondisci)\b",
        # Feedback/correzioni
        r"\b(no[,\s]|non intend|sbagliato|errato|falso|inventato|finto)\b",
        r"\b(invece|piuttosto|preferisco|meglio)\b",
        # Confronti e varianti
        r"^e\s",  # "E a Milano?"
        r"^ma\s",  # "Ma non quelli..."
        r"^solo\s",  # "Solo diretti"
        r"^anche\s",  # "Anche per..."
        # Pronomi inglesi (supporto bilingue)
        r"\b(those|these|that one|the same|it|them)\b",
        r"\b(instead|rather|also|but not)\b",
    ]

    def __init__(
        self,
        llm_client: "NanoGPTClient",
        model: str = REWRITER_MODEL,
    ) -> None:
        """Inizializza il Context-Aware Rewriter.

        Args:
            llm_client: NanoGPT client per chiamate LLM
            model: Modello da usare per il rewriting
        """
        self._llm = llm_client
        self._model = model
        # Compila regex una volta sola
        self._follow_up_patterns = [
            re.compile(p, re.IGNORECASE) for p in self._FOLLOW_UP_INDICATORS
        ]

    async def rewrite(
        self,
        query: str,
        conversation_history: list[dict[str, Any]],
        session_entities: list[str] | None = None,
    ) -> RewriteResult:
        """Riscrive la query integrando il contesto conversazionale.

        Args:
            query: Query corrente dell'utente
            conversation_history: Ultimi messaggi [{role, content, ...}]
            session_entities: Entità tracciate dal grafo NetworkX (opzionale)

        Returns:
            RewriteResult con query riscritta o originale se non necessario
        """
        # ── Check 1: Serve cronologia? ──
        if not conversation_history or len(conversation_history) < self.MIN_HISTORY_TURNS:
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                reason="no_history",
            )

        # ── Check 2: Heuristic — è una follow-up? ──
        if not self._needs_rewriting(query, conversation_history):
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                reason="self_contained",
            )

        # ── Step 3: LLM Rewriting ──
        try:
            rewritten = await self._llm_rewrite(query, conversation_history, session_entities)

            logger.info(
                "query_rewritten",
                original=query[:80],
                rewritten=rewritten[:80],
                history_turns=len(conversation_history),
                entities=session_entities[:5] if session_entities else [],
            )

            return RewriteResult(
                original_query=query,
                rewritten_query=rewritten,
                was_rewritten=True,
                reason="context_integrated",
                session_entities=session_entities or [],
            )

        except Exception as e:
            logger.warning(
                "query_rewrite_failed",
                error=str(e),
                fallback="original_query",
            )
            # Fallback sicuro: usa query originale
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                reason=f"rewrite_error: {e}",
            )

    def _needs_rewriting(
        self,
        query: str,
        conversation_history: list[dict[str, Any]],
    ) -> bool:
        """Heuristic: decide se la query necessita di rewriting.

        Usa una combinazione di segnali per decidere:
        - Presenza di pronomi/riferimenti anaforici
        - Query corta (tipica di follow-up)
        - Assenza di contesto esplicito sufficiente

        Returns:
            True se il rewriting è raccomandato
        """
        query_lower = query.lower().strip()

        # Query molto corta → quasi certamente follow-up
        word_count = len(query.split())
        if word_count <= 5:
            return True

        # Contiene indicatori di follow-up?
        for pattern in self._follow_up_patterns:
            if pattern.search(query_lower):
                return True

        # Query inizia con congiunzione → continuazione
        if query_lower.startswith(("e ", "ma ", "però ", "o ", "oppure ")):
            return True

        # Query non contiene sostantivi specifici ma la history sì
        # (euristica: se la query ha <3 sostantivi e la storia ne ha molti)
        if word_count < 12 and len(conversation_history) >= 2:
            # Se la storia ha molte parole e la query poche, è probabilmente follow-up
            last_user_msg = next(
                (m["content"] for m in reversed(conversation_history) if m.get("role") == "human"),
                "",
            )
            if len(last_user_msg.split()) > word_count * 2:
                return True

        return False

    async def _llm_rewrite(
        self,
        query: str,
        conversation_history: list[dict[str, Any]],
        session_entities: list[str] | None = None,
    ) -> str:
        """Riscrive la query usando LLM con contesto conversazionale.

        Args:
            query: Query corrente
            conversation_history: Messaggi precedenti
            session_entities: Entità dal grafo (opzionale)

        Returns:
            Query riscritta self-contained
        """
        from me4brain.llm.models import LLMRequest, Message, MessageRole

        # Costruisci la cronologia condensata per il prompt
        history_text = self._format_history(conversation_history)

        # Aggiungi entità se disponibili
        entity_hint = ""
        if session_entities:
            entity_hint = f"\n\nEntità chiave della sessione: {', '.join(session_entities[:10])}"

        user_prompt = f"Conversazione:{entity_hint}\n{history_text}\n\nNuova domanda: {query}\n\n→"

        response = await self._llm.generate_response(
            LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=REWRITE_SYSTEM_PROMPT),
                    Message(role=MessageRole.USER, content=user_prompt),
                ],
                model=self._model,
                temperature=0.0,  # Deterministic — vogliamo precisione
                max_tokens=500,  # Le query riscritte sono brevi
            )
        )

        rewritten = response.content.strip()

        # Pulizia: rimuovi eventuali "→" o prefissi residui
        if rewritten.startswith("→"):
            rewritten = rewritten[1:].strip()
        if rewritten.startswith('"') and rewritten.endswith('"'):
            rewritten = rewritten[1:-1].strip()

        # Sanity check: se il rewriting è vuoto o troppo corto, usa originale
        if not rewritten or len(rewritten) < 5:
            logger.warning("rewrite_too_short", rewritten=rewritten, using="original")
            return query

        return rewritten

    def _format_history(
        self,
        conversation_history: list[dict[str, Any]],
    ) -> str:
        """Formatta la cronologia per il prompt di rewriting.

        Usa sliding window: ultimi N turni con contenuto troncato.

        Args:
            conversation_history: Messaggi della sessione

        Returns:
            Stringa formattata della conversazione
        """
        # Prendi gli ultimi MAX_HISTORY_TURNS messaggi
        recent = conversation_history[-self.MAX_HISTORY_TURNS :]

        lines: list[str] = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Tronca contenuto lungo
            if len(content) > self.MAX_CONTENT_PER_TURN:
                content = content[: self.MAX_CONTENT_PER_TURN] + "..."

            role_label = "Utente" if role == "human" else "Assistente"
            lines.append(f"{role_label}: {content}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_rewriter_instance: ContextAwareRewriter | None = None


def get_context_rewriter(llm_client: "NanoGPTClient | None" = None) -> ContextAwareRewriter:
    """Ottiene l'istanza singleton del Context-Aware Rewriter.

    Args:
        llm_client: NanoGPT client (richiesto alla prima chiamata)

    Returns:
        Istanza ContextAwareRewriter
    """
    global _rewriter_instance
    if _rewriter_instance is None:
        if llm_client is None:
            from me4brain.llm.provider_factory import get_reasoning_client

            # CRITICAL FIX: get_reasoning_client() is async and must be awaited
            # Since this function is sync, we must raise an error instead
            raise RuntimeError(
                "get_context_rewriter() called without llm_client in sync context. "
                "Use async get_context_rewriter_async() instead."
            )

        # Usa il modello corretto dalla config
        from me4brain.llm.config import get_llm_config

        config = get_llm_config()
        model = config.ollama_model if config.use_local_tool_calling else REWRITER_MODEL

        _rewriter_instance = ContextAwareRewriter(llm_client, model=model)
    return _rewriter_instance
