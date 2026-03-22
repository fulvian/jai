"""Stage 1: Domain Classification.

Classifies user queries into relevant domains with estimated complexity.
Uses a lightweight LLM call to determine which tool domains are needed.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Any

import structlog

from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainComplexity,
    HybridRouterConfig,
)
from me4brain.engine.hybrid_router.trace_contract import (
    StageTrace,
    StageType,
    FallbackType,
    create_stage_trace,
)
from me4brain.llm.nanogpt import NanoGPTClient
from me4brain.utils.json_utils import robust_json_parse

logger = structlog.get_logger(__name__)


class DomainClassifier:
    """Classifies queries into relevant domains.

    Stage 1 of the hybrid router - determines which domains are relevant
    for a query before selecting specific tools.
    """

    def __init__(
        self,
        llm_client: NanoGPTClient,
        available_domains: list[str],
        config: HybridRouterConfig | None = None,
    ) -> None:
        self._llm = llm_client
        self._domains = available_domains
        self._config = config or HybridRouterConfig()

    def _build_router_prompt(self, current_datetime: str) -> str:
        """Build the system prompt for domain classification."""
        domain_list = ", ".join([f'"{d}"' for d in self._domains])

        return f"""You are a DOMAIN CLASSIFIER for tool selection. Analyze the user query and identify relevant domains.

## YOUR TASK
Analyze the user's request and determine which domains (categories of tools) are relevant.

## AVAILABLE DOMAINS
{domain_list}

## HOW TO ANALYZE
1. First, understand what the user is asking for
2. Then, match their needs to the available domains
3. If uncertain, indicate lower confidence
4. For multi-domain queries, list ALL relevant domains

## COMPLEXITY LEVELS
- "low": Simple query, 1-3 tools needed
- "medium": Moderate query, 4-8 tools needed
- "high": Complex query, 8+ tools or multiple steps

## EXAMPLES

Query: "meteo a Milano e prezzo Bitcoin oggi"
→ {{"domains": [{{"name": "geo_weather", "complexity": "low"}}, {{"name": "finance_crypto", "complexity": "medium"}}], "confidence": 0.98, "query_summary": "Weather + crypto price query"}}

Query: "crea evento calendario domani alle 10, invia email a Mario e cerca file progetto X"
→ {{"domains": [{{"name": "google_workspace", "complexity": "medium"}}, {{"name": "productivity", "complexity": "low"}}], "confidence": 0.95, "query_summary": "Multi-operation G-Suite request"}}

Query: "cerca informazioni su machine learning e papers su arXiv"
→ {{"domains": [{{"name": "web_search", "complexity": "medium"}}, {{"name": "science_research", "complexity": "low"}}], "confidence": 0.85, "query_summary": "Search + scientific research query"}}

Query: "Qual è il senso della vita?"
→ {{"domains": [], "confidence": 0.9, "query_summary": "Philosophical question, no tools needed"}}

Query: "analisi tecnica AAPL con RSI e MACD, confronta con metriche fondamentali"
→ {{"domains": [{{"name": "finance_crypto", "complexity": "high"}}], "confidence": 0.95, "query_summary": "Complex financial analysis request"}}

Query: "pronostico Lakers vs Celtics, value bet e sistema di scommesse NBA"
→ {{"domains": [{{"name": "sports_nba", "complexity": "high"}}], "confidence": 0.95, "query_summary": "NBA betting analysis and predictions"}}

Query: "prenota campo da tennis per domani alle 18"
→ {{"domains": [{{"name": "sports_booking", "complexity": "low"}}], "confidence": 0.98, "query_summary": "Sports facility booking"}}

Query: "trova ristoranti stellati a Parigi e prenota per due"
→ {{"domains": [{{"name": "food", "complexity": "medium"}}], "confidence": 0.95, "query_summary": "Food and restaurant search"}}

Query: "organizza un viaggio a Tokyo: voli, hotel e attività"
→ {{"domains": [{{"name": "travel", "complexity": "high"}}], "confidence": 0.95, "query_summary": "Complex travel planning"}}

Query: "ogni giorno analizza HOG e decidi buy/sell"
→ {{"domains": [{{"name": "utility", "complexity": "low"}}], "confidence": 0.95, "query_summary": "Scheduled recurring task setup"}}

Query: "cerca offerta di lavoro come Senior AI Engineer a Milano"
→ {{"domains": [{{"name": "jobs", "complexity": "low"}}], "confidence": 0.95, "query_summary": "Job search query"}}

Query: "i sintomi del diabete e ultime news mediche"
→ {{"domains": [{{"name": "medical", "complexity": "medium"}}, {{"name": "knowledge_media", "complexity": "low"}}], "confidence": 0.95, "query_summary": "Medical info and recent news search"}}

DISAMBIGUATION:
- "scommesse", "betting", "pronostico", "odds", "value bet", "spread", "over/under" → ALWAYS "sports_nba", NEVER "finance_crypto"
- "finance_crypto" is for stocks, crypto, trading, forex, ETF, bonds — NOT sports betting
- "google_workspace" is for all G-Suite tools (Drive, Docs, Sheets, Gmail, Calendar, Meet)
- "productivity" is for miscellaneous tasks, reminders, and notes outside G-Suite

Current time: {current_datetime}"""

    async def classify(
        self,
        query: str,
        conversation_context: list[dict[str, Any]] | None = None,
        intent_analysis: dict[str, Any] | None = None,
    ) -> DomainClassification:
        """Classify a query into relevant domains.

        Args:
            query: User query to classify
            conversation_context: Recent conversation history for context
            intent_analysis: Optional pre-analysis from IntentAnalyzer

        Returns:
            DomainClassification with domains, complexity, and confidence
        """
        from me4brain.llm.models import LLMRequest, Message, MessageRole

        current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_prompt = self._build_router_prompt(current_dt)

        # Build user content with context
        user_content = f"USER QUERY: {query}"

        # Add conversation context if available
        if conversation_context and len(conversation_context) > 0:
            context_summary = self._summarize_context(conversation_context)
            user_content = f"CONVERSATION CONTEXT:\n{context_summary}\n\n{user_content}"

        # Add intent hints if available
        if intent_analysis:
            suggested = intent_analysis.get("suggested_domains", [])
            if suggested:
                user_content += f"\n\nHINT: Intent analysis suggests these domains: {suggested}"

        user_content += "\n\nRespond with JSON:"

        try:
            # Build LLMRequest for NanoGPTClient.generate_response()
            request = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=system_prompt),
                    Message(role=MessageRole.USER, content=user_content),
                ],
                model=self._config.router_model,
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=200,  # Classification is short
            )

            # Wrap LLM call with timeout protection (600 seconds for classification - generous development phase)
            try:
                response = await asyncio.wait_for(
                    self._llm.generate_response(request),
                    timeout=600.0,  # 600 second timeout for domain classification (development)
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "domain_classification_timeout",
                    timeout_seconds=600,
                    fallback="keyword_based",
                    query_preview=query[:50],
                )
                return self._fallback_classification(query)

            content = response.choices[0].message.content or ""
            content = content.strip()

            logger.debug("domain_classification_raw_output", content=content)

            # Add JSON recovery for partial/multi-line responses
            # This helps if the LLM response is incomplete or has whitespace issues
            if not content:
                logger.warning(
                    "domain_classification_empty_response",
                    query_preview=query[:50],
                )
                return self._fallback_classification(query)

            data = robust_json_parse(content, expect_object=True)

            if not data:
                logger.warning(
                    "domain_classification_json_error",
                    query_preview=query[:50],
                    content_preview=content[:100],
                )
                return self._fallback_classification(query)

            try:
                domains = []
                for d in data.get("domains", []):
                    if isinstance(d, dict):
                        domains.append(
                            DomainComplexity(
                                name=d.get("name", "unknown"),
                                complexity=d.get("complexity", "medium"),
                            )
                        )
                    elif isinstance(d, str):
                        domains.append(DomainComplexity(name=d, complexity="medium"))

                classification = DomainClassification(
                    domains=domains,
                    confidence=data.get("confidence", 0.8),
                    query_summary=data.get("query_summary", ""),
                )

                logger.info(
                    "domain_classification_complete",
                    query_preview=query[:50],
                    domains=[d.name for d in domains],
                    confidence=classification.confidence,
                    is_multi_domain=classification.is_multi_domain,
                )

                return classification

            except Exception as e:
                logger.warning(
                    "domain_classification_parse_error",
                    error=str(e),
                    query_preview=query[:50],
                )
                return self._fallback_classification(query)

        except Exception as e:
            logger.error(
                "domain_classification_failed",
                error=str(e),
                query_preview=query[:50],
            )
            return self._fallback_classification(query)

    async def classify_with_trace(
        self,
        query: str,
        conversation_context: list[dict[str, Any]] | None = None,
        intent_analysis: dict[str, Any] | None = None,
    ) -> tuple[DomainClassification, StageTrace]:
        """Classify a query and return structured trace for observability.

        Phase A (Instrumentation): Returns both classification AND trace contract
        for complete observability of domain classification stage.

        Args:
            query: User query to classify
            conversation_context: Recent conversation history for context
            intent_analysis: Optional pre-analysis from IntentAnalyzer

        Returns:
            Tuple of (DomainClassification, StageTrace) for full observability
        """
        from me4brain.llm.models import LLMRequest, Message, MessageRole

        start_time = time.time()
        trace = StageTrace(
            stage=StageType.STAGE_1,
            model_requested=self._config.router_model,
            input_query=query,
        )

        try:
            current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_prompt = self._build_router_prompt(current_dt)

            # Build user content with context
            user_content = f"USER QUERY: {query}"

            # Add conversation context if available
            if conversation_context and len(conversation_context) > 0:
                context_summary = self._summarize_context(conversation_context)
                user_content = f"CONVERSATION CONTEXT:\n{context_summary}\n\n{user_content}"

            # Add intent hints if available
            if intent_analysis:
                suggested = intent_analysis.get("suggested_domains", [])
                if suggested:
                    user_content += f"\n\nHINT: Intent analysis suggests these domains: {suggested}"

            user_content += "\n\nRespond with JSON:"

            try:
                # Build LLMRequest for NanoGPTClient.generate_response()
                request = LLMRequest(
                    messages=[
                        Message(role=MessageRole.SYSTEM, content=system_prompt),
                        Message(role=MessageRole.USER, content=user_content),
                    ],
                    model=self._config.router_model,
                    temperature=0.1,  # Low temperature for consistent classification
                    max_tokens=200,  # Classification is short
                )

                # Wrap LLM call with timeout protection
                try:
                    response = await asyncio.wait_for(
                        self._llm.generate_response(request),
                        timeout=600.0,
                    )
                    trace.provider_resolved = getattr(self._llm, "provider", "unknown")
                    trace.model_effective = self._config.router_model

                except asyncio.TimeoutError:
                    trace.fallback_applied = True
                    trace.fallback_type = FallbackType.LLM_TIMEOUT
                    trace.fallback_reason = "Domain classification LLM timeout (600s)"
                    trace.success = False
                    trace.error_code = "TIMEOUT"
                    trace.error_message = "LLM timeout after 600 seconds"
                    trace.duration_ms = (time.time() - start_time) * 1000

                    logger.warning(
                        "domain_classification_timeout",
                        timeout_seconds=600,
                        fallback="keyword_based",
                        query_preview=query[:50],
                    )
                    classification = self._fallback_classification(query)
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence
                    trace.used_fallback_keywords = True
                    return classification, trace

                content = response.choices[0].message.content or ""
                content = content.strip()

                logger.debug("domain_classification_raw_output", content=content)

                # Handle empty response
                if not content:
                    trace.fallback_applied = True
                    trace.fallback_type = FallbackType.LLM_PARSE_ERROR
                    trace.fallback_reason = "Empty LLM response"
                    trace.success = False
                    trace.error_code = "EMPTY_RESPONSE"
                    trace.error_message = "LLM returned empty content"
                    trace.duration_ms = (time.time() - start_time) * 1000

                    logger.warning(
                        "domain_classification_empty_response",
                        query_preview=query[:50],
                    )
                    classification = self._fallback_classification(query)
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence
                    trace.used_fallback_keywords = True
                    return classification, trace

                # Parse JSON
                data = robust_json_parse(content, expect_object=True)

                if not data:
                    trace.fallback_applied = True
                    trace.fallback_type = FallbackType.LLM_PARSE_ERROR
                    trace.fallback_reason = "JSON parse failed"
                    trace.success = False
                    trace.error_code = "JSON_PARSE_ERROR"
                    trace.error_message = f"Failed to parse JSON from: {content[:100]}"
                    trace.duration_ms = (time.time() - start_time) * 1000

                    logger.warning(
                        "domain_classification_json_error",
                        query_preview=query[:50],
                        content_preview=content[:100],
                    )
                    classification = self._fallback_classification(query)
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence
                    trace.used_fallback_keywords = True
                    return classification, trace

                try:
                    domains = []
                    for d in data.get("domains", []):
                        if isinstance(d, dict):
                            domains.append(
                                DomainComplexity(
                                    name=d.get("name", "unknown"),
                                    complexity=d.get("complexity", "medium"),
                                )
                            )
                        elif isinstance(d, str):
                            domains.append(DomainComplexity(name=d, complexity="medium"))

                    classification = DomainClassification(
                        domains=domains,
                        confidence=data.get("confidence", 0.8),
                        query_summary=data.get("query_summary", ""),
                    )

                    # Trace success
                    trace.success = True
                    trace.fallback_applied = False
                    trace.fallback_type = FallbackType.NONE
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence

                    logger.info(
                        "domain_classification_complete",
                        query_preview=query[:50],
                        domains=[d.name for d in domains],
                        confidence=classification.confidence,
                        is_multi_domain=classification.is_multi_domain,
                    )

                    trace.duration_ms = (time.time() - start_time) * 1000
                    return classification, trace

                except Exception as e:
                    trace.fallback_applied = True
                    trace.fallback_type = FallbackType.LLM_PARSE_ERROR
                    trace.fallback_reason = f"Classification parse error: {str(e)}"
                    trace.success = False
                    trace.error_code = "PARSE_ERROR"
                    trace.error_message = str(e)
                    trace.duration_ms = (time.time() - start_time) * 1000

                    logger.warning(
                        "domain_classification_parse_error",
                        error=str(e),
                        query_preview=query[:50],
                    )
                    classification = self._fallback_classification(query)
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence
                    trace.used_fallback_keywords = True
                    return classification, trace

            except asyncio.TimeoutError:
                # Timeout during generation_response
                trace.fallback_applied = True
                trace.fallback_type = FallbackType.LLM_TIMEOUT
                trace.fallback_reason = "LLM generation timeout"
                trace.success = False
                trace.error_code = "TIMEOUT"
                trace.error_message = "generate_response timed out"
                trace.duration_ms = (time.time() - start_time) * 1000

                classification = self._fallback_classification(query)
                trace.output_domains = classification.domain_names
                trace.output_count = len(classification.domain_names)
                trace.confidence_score = classification.confidence
                trace.used_fallback_keywords = True
                return classification, trace

        except Exception as e:
            trace.fallback_applied = True
            trace.fallback_type = FallbackType.LLM_EXCEPTION
            trace.fallback_reason = f"Unhandled exception: {str(e)}"
            trace.success = False
            trace.error_code = "EXCEPTION"
            trace.error_message = str(e)
            trace.duration_ms = (time.time() - start_time) * 1000

            logger.error(
                "domain_classification_failed",
                error=str(e),
                query_preview=query[:50],
            )
            classification = self._fallback_classification(query)
            trace.output_domains = classification.domain_names
            trace.output_count = len(classification.domain_names)
            trace.confidence_score = classification.confidence
            trace.used_fallback_keywords = True
            return classification, trace

    def _fallback_classification(self, query: str) -> DomainClassification:
        """Generate fallback classification when LLM fails.

        Uses keyword-based domain detection instead of generic web_search.
        """
        query_lower = query.lower()
        detected_domains: list[str] = []

        KEYWORD_DOMAIN_MAP = {
            "geo_weather": [
                "meteo",
                "tempo",
                "pioggia",
                "temperatura",
                "weather",
                "forecast",
                "neve",
                "vento",
            ],
            "finance_crypto": [
                "prezzo",
                "bitcoin",
                "crypto",
                "azioni",
                "stock",
                "borsa",
                "trading",
                "ethereum",
                "finanza",
                # NOTE: "scommesse", "betting", "odds" removed - these belong to sports_nba
            ],
            "web_search": ["cerca", "trova", "search", "find", "ricerca", "notizie", "news"],
            "google_workspace": [
                "email",
                "mail",
                "gmail",
                "calendar",
                "calendario",
                "drive",
                "documento",
                "doc",
                "sheet",
                "foglio",
            ],
            "productivity": ["promemoria", "reminder", "nota", "task", "attività", "appuntamento"],
            "travel": ["volo", "hotel", "viaggio", "prenota", "flight", "booking", "aeroporto"],
            "food": ["ristorante", "mangiare", "pizza", "cibo", "restaurant", "menu"],
            "sports_nba": [
                # Core NBA keywords
                "nba",
                "basket",
                "basketball",
                "partita",
                "partite",
                # Italian betting keywords (B4 FIX: expanded)
                "scommessa",
                "scommesse",  # PLURAL - was missing
                "pronostico",
                "pronostici",  # PLURAL
                "sistema scommesse",
                "value bet",
                # English betting keywords (B4 FIX: added)
                "betting",
                "bet",
                "bets",
                "odds",
                "spread",
                "over/under",
                "over under",
                "moneyline",
                "point spread",
                "betting lines",
                "betting tips",
                "picks",
                "predictions",
                "wager",
                # Italian betting-related
                "analisi scommesse",
                "pronostico vincente",
                "sistema vincente",
                # Team names (common)
                "lakers",
                "celtics",
                "warriors",
                "bulls",
                "heat",
                "knicks",
                "nets",
                "bucks",
                "nuggets",
                "suns",
                "76ers",
                "sixers",
            ],
            "sports_booking": ["campo", "tennis", "calcetto", "padel", "prenotare campo"],
            "science_research": ["paper", "ricerca", "arxiv", "pubmed", "scientifico", "studio"],
            "medical": ["farmaco", "medico", "sintomo", "salute", "medicina", "dottore"],
            "entertainment": ["film", "musica", "cinema", "netflix", "spotify", "serie tv"],
            "shopping": ["comprare", "amazon", "negozio", "shop", "acquista"],
        }

        for domain, keywords in KEYWORD_DOMAIN_MAP.items():
            if any(kw in query_lower for kw in keywords):
                if domain in self._domains:
                    detected_domains.append(domain)

        if not detected_domains:
            detected_domains = self._config.fallback_domains

        return DomainClassification(
            domains=[DomainComplexity(name=d, complexity="medium") for d in detected_domains[:3]],
            confidence=0.6,
            query_summary="Fallback classification via keyword detection",
        )

    async def classify_with_fallback(
        self,
        query: str,
        conversation_context: list[dict[str, Any]] | None = None,
        intent_analysis: dict[str, Any] | None = None,
    ) -> tuple[DomainClassification, bool]:
        """Classify with automatic fallback handling.

        Returns:
            Tuple of (classification, was_fallback_applied)
        """
        classification = await self.classify(query, conversation_context, intent_analysis)

        if classification.needs_fallback:
            # Low confidence or no domains - add fallback
            logger.info(
                "applying_classification_fallback",
                original_domains=classification.domain_names,
                confidence=classification.confidence,
            )

            # Add fallback domains if not already present
            fallback_domains = []
            existing_names = set(classification.domain_names)

            for fb_domain in self._config.fallback_domains:
                if fb_domain not in existing_names:
                    fallback_domains.append(DomainComplexity(name=fb_domain, complexity="medium"))

            # Create new classification with fallbacks
            new_classification = DomainClassification(
                domains=classification.domains + fallback_domains,
                confidence=classification.confidence,
                query_summary=classification.query_summary,
            )

            return new_classification, True

        return classification, False

    def _summarize_context(self, conversation_context: list[dict[str, Any]]) -> str:
        """Summarize conversation context for the prompt.

        Takes the last few turns and formats them concisely.
        """
        # Take last 3 turns max
        recent = conversation_context[-3:] if conversation_context else []
        lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:150]  # Truncate
            role_label = "User" if role in ("user", "human") else "Assistant"
            lines.append(f"{role_label}: {content}")

        return "\n".join(lines)
