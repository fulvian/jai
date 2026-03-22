"""Conversational Query Detection.

Detects pure conversational queries that don't require tool usage.
Uses a two-stage approach:
1. Fast path: regex pattern matching (< 1ms)
2. Slow path: LLM classification for ambiguous queries (~50-100ms)

This module enables the "conversational bypass" pattern where simple
conversational queries bypass the tool routing engine entirely.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from me4brain.llm.base import LLMProvider

logger = structlog.get_logger(__name__)


class ConversationalDetector:
    """Detects pure conversational queries that don't require tools.

    Pattern: SOTA 2026 for agentic systems. Distinguishes between:
    - Conversational queries: "ciao", "come stai", "chi sei"
    - Tool-required queries: "cerca", "prezzo", "meteo", "invia email"
    - Hybrid queries: "raccogli dati e analizza" (requires decomposition)
    """

    # Fast-path regex patterns for common conversational intents
    CONVERSATIONAL_PATTERNS = {
        "greeting": r"^(ciao|hello|hi|salve|ehi|buongiorno|buonasera|hey|yo)",
        "farewell": r"(arrivederci|addio|bye|ciao|goodbye|grazie|thanks|grazie mille|thank you)",
        "small_talk": r"(come stai|how are you|come va|what's up|che novità|come ti chiami|what's your name)",
        "meta_about_bot": r"(chi sei|what are you|cosa puoi fare|what can you do|come funzioni|how do you work)",
        "opinion_ask": r"(cosa pensi|what do you think|credi che|do you think|secondo te)",
        "joke_request": r"(raccontami una barzelletta|tell me a joke|dimmi una battuta)",
    }

    def __init__(self) -> None:
        """Initialize the conversational detector."""
        pass

    async def is_conversational(
        self,
        query: str,
        llm_client: "LLMProvider",
    ) -> tuple[bool, str]:
        """Determine if a query is pure conversation.

        Args:
            query: User query to classify
            llm_client: LLM client for LLM-based classification (local or cloud)

        Returns:
            (is_conversational, reason) where reason explains the classification
        """
        # Fast path: regex patterns (< 1ms)
        for pattern_type, regex in self.CONVERSATIONAL_PATTERNS.items():
            if re.match(regex, query.strip(), re.IGNORECASE | re.UNICODE):
                logger.debug(
                    "conversational_detected_fast_path",
                    pattern_type=pattern_type,
                    query_preview=query[:50],
                )
                return True, f"matched_pattern:{pattern_type}"

        # Slow path: LLM classification for ambiguous queries (~50-100ms)
        word_count = len(query.split())
        logger.debug(
            "conversational_detection_slow_path",
            query_preview=query[:50],
            word_count=word_count,
        )

        try:
            from me4brain.llm.models import LLMRequest, Message, MessageRole
            from me4brain.llm.config import get_llm_config

            config = get_llm_config()
            prompt = f"""Classifica se questa query richiede tools/API call o è pura conversazione.

REGOLA FONDAMENTALE: La lunghezza della query NON determina se è conversazionale.
Una query corta può richiedere dati reali (meteo, prezzi, notizie) → NON conversazionale.
Una query lunga può essere una chiacchierata → conversazionale.

Esempi di query CORTE ma che richiedono tools (is_conversational: false):
- "che tempo fa a Roma?" → richiede API meteo
- "prezzo bitcoin oggi" → richiede API prezzi
- "terremoti recenti" → richiede API USGS
- "notizie di oggi" → richiede API news
- "dove si trova Milano?" → richiede API geocoding

Esempi di query conversazionali (is_conversational: true):
- "grazie" → puro ringraziamento
- "cosa pensi di questo?" → opinione, no tool
- "spiegami cos'è l'AI" → domanda conoscitiva, no dati live

Query: "{query}"

Rispondi SOLO con JSON valido (niente altro):
{{"is_conversational": true/false, "reason": "breve spiegazione"}}"""

            config = get_llm_config()
            # Usa il modello configurato per il provider locale
            model = config.ollama_model if config.use_local_tool_calling else config.model_routing
            response = await llm_client.generate_response(
                LLMRequest(
                    messages=[
                        Message(role=MessageRole.USER, content=prompt),
                    ],
                    model=model,
                    temperature=0.1,
                    max_tokens=100,
                )
            )

            if not response.choices or not response.choices[0].message.content:
                logger.warning(
                    "conversational_detection_empty_response",
                    query_preview=query[:50],
                )
                return False, "llm_empty_response"

            # Parse JSON response
            try:
                result = json.loads(response.choices[0].message.content)
                is_conv = result.get("is_conversational", False)
                reason = result.get("reason", "llm_classification")

                logger.debug(
                    "conversational_detected_llm_path",
                    is_conversational=is_conv,
                    reason=reason,
                    query_preview=query[:50],
                )

                return is_conv, f"llm_classification:{reason}"

            except json.JSONDecodeError as e:
                logger.warning(
                    "conversational_detection_json_parse_failed",
                    error=str(e),
                    response_preview=response.choices[0].message.content[:100],
                )
                return False, "llm_json_parse_failed"

        except Exception as e:
            logger.error(
                "conversational_detection_failed",
                error=str(e),
                error_type=type(e).__name__,
                query_preview=query[:50],
            )
            # Fallback: assume not conversational on error
            return False, f"detection_error:{type(e).__name__}"
