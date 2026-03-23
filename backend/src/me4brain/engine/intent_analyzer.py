"""Intent Analyzer - Semantic Intent Understanding Layer.

Analyzes user queries to understand INTENT before domain classification.
This solves the systemic problem where keyword-based systems fail to
understand what the user actually wants.

Key Principles:
1. Semantic understanding, not keyword matching
2. Allow uncertainty - LLM can express low confidence
3. Conversation context-aware
4. Domain-agnostic - works for weather, crypto, search, sports, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from me4brain.utils.json_utils import robust_json_parse

if TYPE_CHECKING:
    from me4brain.llm.nanogpt import NanoGPTClient

logger = structlog.get_logger(__name__)


class IntentType(str, Enum):
    """Types of user intent."""

    DATA_RETRIEVAL = "data_retrieval"  # User wants data/info (prices, weather, facts)
    ACTION = "action"  # User wants something done (send email, create doc)
    CONVERSATION = "conversation"  # Casual chat, greetings, opinions
    CLARIFICATION = "clarification"  # Follow-up question about previous response
    MULTI_INTENT = "multi_intent"  # Multiple distinct requests in one query


class DataRequirement(str, Enum):
    """Types of data requirements."""

    REAL_TIME = "real_time"  # Current prices, weather, live data
    HISTORICAL = "historical"  # Past data, trends
    GENERAL_INFO = "general_info"  # Static knowledge, definitions
    EXTERNAL_API = "external_api"  # Requires calling external service
    NONE = "none"  # No external data needed


@dataclass
class DataRequirements:
    """Analysis of what data the query needs."""

    needs_real_time_data: bool = False
    needs_historical_data: bool = False
    needs_external_api: bool = False
    primary_requirement: DataRequirement = DataRequirement.NONE
    details: str = ""


@dataclass
class IntentAnalysis:
    """Result of intent analysis."""

    intent_type: IntentType
    data_requirements: DataRequirements
    confidence: float
    reasoning: str = ""
    clarification_needed: bool = False
    clarification_question: str | None = None
    detected_entities: list[str] = field(default_factory=list)
    suggested_domains: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt for Intent Analysis (more natural, less rigid)
# ---------------------------------------------------------------------------

INTENT_ANALYSIS_PROMPT = """Analizza questa richiesta dell'utente e comprendi cosa sta chiedendo.

DATA ORA CORRENTE: {current_datetime}

CONTESTO CONVERSAZIONALE (ultimi turni):
{conversation_summary}

RICHIESTA UTENTE: "{query}"

---

Analizza la richiesta e rispondi alle seguenti domande:

1. **INTENTO PRINCIPALE**: Cosa vuole ottenere l'utente?
   - "data_retrieval": vuole informazioni/dati (prezzi, meteo, fatti)
   - "action": vuole che il sistema faccia qualcosa (invia email, crea doc)
   - "conversation": chiacchierare, saluti, opinioni
   - "clarification": domanda di follow-up su risposta precedente
   - "multi_intent": più richieste distinte in una query

2. **TIPO DI DATI**: Di che tipo di dati ha bisogno?
   - Dati in tempo reale? (prezzi attuali, meteo ora)
   - Dati storici? (trend, dati passati)
   - Informazioni generali? (conoscenza statica)
   - API esterne? (servizi web, database)

3. **ENTITÀ RILEVANTI**: Quali entità specifiche sono menzionate?
   - Luoghi, aziende, criptovalute, persone, date, ecc.

4. **DOMINI SUGGERITI**: Quali domini di tool sarebbero rilevanti?
   - Esempi: geo_weather, finance_crypto, web_search, sports_nba, ecc.

5. **AMBIGUITÀ**: C'è qualcosa di poco chiaro che richiede chiarimenti?

---

Rispondi in questo formato JSON:
{{
  "intent_type": "data_retrieval" | "action" | "conversation" | "clarification" | "multi_intent",
  "data_requirements": {{
    "needs_real_time_data": true/false,
    "needs_historical_data": true/false,
    "needs_external_api": true/false,
    "primary_requirement": "real_time" | "historical" | "general_info" | "external_api" | "none",
    "details": "breve descrizione"
  }},
  "confidence": 0.0-1.0,
  "reasoning": "spiegazione breve del ragionamento",
  "clarification_needed": true/false,
  "clarification_question": "domanda di chiarimento se necessaria",
  "detected_entities": ["entità1", "entità2"],
  "suggested_domains": ["dominio1", "dominio2"]
}}

IMPORTANTE:
- Se la query menziona luoghi + tempo/meteo → geo_weather
- Se la query menziona prezzi, criptovalute, azioni → finance_crypto
- Se la query menziona "cerca", "trova", "notizie" → web_search
- Se non sei sicuro, indica confidence bassa (< 0.7)
- Se la query è ambigua, suggerisci una domanda di chiarimento
"""


class IntentAnalyzer:
    """Analyzes user intent semantically before domain classification.

    This is the FIRST layer of understanding - it determines WHAT the user
    wants before we try to determine WHICH tools to use.

    Usage:
        analyzer = IntentAnalyzer(llm_client)
        analysis = await analyzer.analyze(query, conversation_context)

        if analysis.data_requirements.needs_real_time_data:
            # Definitely need tools
            pass
        if analysis.intent_type == "conversation":
            # No tools needed, just chat
            pass
    """

    def __init__(
        self,
        llm_client: NanoGPTClient,
        model: str = "deepseek/deepseek-chat-v3-0324",
    ) -> None:
        """Initialize the Intent Analyzer.

        Args:
            llm_client: NanoGPT client for LLM calls
            model: Model to use for intent analysis (fast, cheap model preferred)
        """
        self._llm = llm_client
        self._model = model

    async def analyze(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> IntentAnalysis:
        """Analyze the user's intent semantically.

        Args:
            query: User's query
            conversation_history: Recent conversation turns for context

        Returns:
            IntentAnalysis with intent type, data requirements, confidence, etc.
        """
        from me4brain.llm.models import LLMRequest, Message, MessageRole

        # Format conversation summary
        conv_summary = self._format_conversation_summary(conversation_history)

        # Build prompt
        current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = INTENT_ANALYSIS_PROMPT.format(
            current_datetime=current_dt,
            conversation_summary=conv_summary,
            query=query,
        )

        try:
            request = LLMRequest(
                messages=[Message(role=MessageRole.USER, content=prompt)],
                model=self._model,
                temperature=0.1,  # Low temperature for consistent analysis
                max_tokens=500,
            )

            response = await self._llm.generate_response(request)
            content = response.choices[0].message.content or ""

            # Parse JSON response
            data = robust_json_parse(content, expect_object=True)

            if not data:
                logger.warning(
                    "intent_analysis_json_parse_failed",
                    query_preview=query[:50],
                    content_preview=content[:200],
                )
                return self._fallback_analysis(query)

            # Build IntentAnalysis from response
            intent_type = IntentType(data.get("intent_type", "data_retrieval"))

            # Parse data requirements
            dr_data = data.get("data_requirements", {})
            data_requirements = DataRequirements(
                needs_real_time_data=dr_data.get("needs_real_time_data", False),
                needs_historical_data=dr_data.get("needs_historical_data", False),
                needs_external_api=dr_data.get("needs_external_api", False),
                primary_requirement=DataRequirement(dr_data.get("primary_requirement", "none")),
                details=dr_data.get("details", ""),
            )

            analysis = IntentAnalysis(
                intent_type=intent_type,
                data_requirements=data_requirements,
                confidence=data.get("confidence", 0.5),
                reasoning=data.get("reasoning", ""),
                clarification_needed=data.get("clarification_needed", False),
                clarification_question=data.get("clarification_question"),
                detected_entities=data.get("detected_entities", []),
                suggested_domains=data.get("suggested_domains", []),
            )

            logger.info(
                "intent_analysis_complete",
                query_preview=query[:50],
                intent_type=intent_type.value,
                needs_real_time=data_requirements.needs_real_time_data,
                needs_external=data_requirements.needs_external_api,
                confidence=analysis.confidence,
                suggested_domains=analysis.suggested_domains,
            )

            return analysis

        except Exception as e:
            logger.error(
                "intent_analysis_failed",
                error=str(e),
                query_preview=query[:50],
            )
            return self._fallback_analysis(query)

    def _format_conversation_summary(
        self,
        conversation_history: list[dict[str, Any]] | None,
    ) -> str:
        """Format conversation history for the prompt."""
        if not conversation_history:
            return "(nessun contesto precedente)"

        # Take last 4 turns max
        recent = conversation_history[-4:]
        lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]  # Truncate long messages
            role_label = "Utente" if role in ("user", "human") else "Assistente"
            lines.append(f"{role_label}: {content}")

        return "\n".join(lines)

    def _fallback_analysis(self, query: str) -> IntentAnalysis:
        """Fallback analysis when LLM fails.

        Uses simple heuristics as last resort.
        """
        query_lower = query.lower()

        # Simple heuristic detection
        needs_real_time = any(
            kw in query_lower
            for kw in [
                "ora",
                "adesso",
                "oggi",
                "prezzo",
                "meteo",
                "tempo",
                "now",
                "today",
                "price",
                "weather",
            ]
        )

        is_conversation = any(
            kw in query_lower for kw in ["ciao", "grazie", "come stai", "hello", "thanks", "hi "]
        )

        intent_type = IntentType.CONVERSATION if is_conversation else IntentType.DATA_RETRIEVAL

        return IntentAnalysis(
            intent_type=intent_type,
            data_requirements=DataRequirements(
                needs_real_time_data=needs_real_time,
                needs_external_api=needs_real_time,
                primary_requirement=DataRequirement.REAL_TIME
                if needs_real_time
                else DataRequirement.NONE,
            ),
            confidence=0.4,  # Low confidence for fallback
            reasoning="Fallback heuristic analysis (LLM failed)",
        )

    def should_use_tools(self, analysis: IntentAnalysis) -> bool:
        """Determine if tools should be used based on intent analysis.

        This replaces keyword-based fallback logic with semantic understanding.

        Args:
            analysis: IntentAnalysis result

        Returns:
            True if tools should be used
        """
        # Never use tools for pure conversation
        if analysis.intent_type == IntentType.CONVERSATION:
            return False

        # Always use tools for real-time data
        if analysis.data_requirements.needs_real_time_data:
            return True

        # Always use tools for external API needs
        if analysis.data_requirements.needs_external_api:
            return True

        # For data retrieval, use tools if confidence is decent
        if analysis.intent_type == IntentType.DATA_RETRIEVAL:
            return analysis.confidence > 0.5

        # For actions, might need tools (email, calendar, etc.)
        if analysis.intent_type == IntentType.ACTION:
            return True

        # Multi-intent likely needs multiple tools
        return analysis.intent_type == IntentType.MULTI_INTENT


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_analyzer_instance: IntentAnalyzer | None = None


def get_intent_analyzer(llm_client: NanoGPTClient | None = None) -> IntentAnalyzer:
    """Get the singleton IntentAnalyzer instance.

    Args:
        llm_client: NanoGPT client (required on first call)

    Returns:
        IntentAnalyzer instance
    """
    global _analyzer_instance
    if _analyzer_instance is None:
        if llm_client is None:
            # CRITICAL FIX: get_reasoning_client() is async and must be awaited
            # Since this function is sync, we must raise an error instead
            raise RuntimeError(
                "get_intent_analyzer() called without llm_client in sync context. "
                "Pass llm_client explicitly."
            )

        # Use local model when configured
        from me4brain.llm.config import get_llm_config

        config = get_llm_config()
        model = (
            config.ollama_model
            if config.use_local_tool_calling
            else "deepseek/deepseek-chat-v3-0324"
        )

        _analyzer_instance = IntentAnalyzer(llm_client, model=model)
    return _analyzer_instance
