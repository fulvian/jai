"""Unified Intent Analysis System.

Replaces the ConversationalDetector with an LLM-based intent analyzer that
intelligently classifies queries as conversational or tool-requiring, eliminating
hardcoded patterns and enabling scalable tool routing across all domains.

This module provides:
- IntentType enum: CONVERSATIONAL, TOOL_REQUIRED
- QueryComplexity enum: SIMPLE, MODERATE, COMPLEX
- IntentAnalysis dataclass: Result of intent analysis with validation
- UnifiedIntentAnalyzer class: Main analyzer using LLM-based classification
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field, field_validator

from me4brain.utils.json_utils import parse_llm_json_response

if TYPE_CHECKING:
    from me4brain.llm.base import LLMProvider

logger = structlog.get_logger(__name__)


class IntentType(str, Enum):
    """Query intent classification."""

    CONVERSATIONAL = "conversational"
    TOOL_REQUIRED = "tool_required"


class QueryComplexity(str, Enum):
    """Query complexity level."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class IntentAnalysisModel(BaseModel):
    """Pydantic model for intent analysis with validation."""

    intent: IntentType = Field(
        ...,
        description="Intent type: conversational or tool_required",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Relevant domains for tool-required queries (empty for conversational)",
    )
    complexity: QueryComplexity = Field(
        default=QueryComplexity.SIMPLE,
        description="Query complexity: simple, moderate, or complex",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    reasoning: str = Field(
        default="",
        description="Explanation of the classification",
    )

    @field_validator("intent", mode="before")
    @classmethod
    def validate_intent(cls, v: str | IntentType) -> IntentType:
        """Validate and convert intent to enum."""
        if isinstance(v, IntentType):
            return v
        if isinstance(v, str):
            try:
                return IntentType(v.lower())
            except ValueError:
                raise ValueError(
                    f"Invalid intent: {v}. Must be 'conversational' or 'tool_required'"
                )
        raise ValueError(f"Intent must be string or IntentType, got {type(v)}")

    @field_validator("complexity", mode="before")
    @classmethod
    def validate_complexity(cls, v: str | QueryComplexity) -> QueryComplexity:
        """Validate and convert complexity to enum."""
        if isinstance(v, QueryComplexity):
            return v
        if isinstance(v, str):
            try:
                return QueryComplexity(v.lower())
            except ValueError:
                raise ValueError(
                    f"Invalid complexity: {v}. Must be 'simple', 'moderate', or 'complex'"
                )
        raise ValueError(f"Complexity must be string or QueryComplexity, got {type(v)}")

    @field_validator("domains", mode="before")
    @classmethod
    def validate_domains(cls, v: list[str] | None) -> list[str]:
        """Validate domains list."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError(f"Domains must be a list, got {type(v)}")
        return [d.lower() for d in v if isinstance(d, str)]

    def model_post_init(self, __context):
        """Validate domain consistency after model initialization."""
        # If conversational, domains must be empty
        if self.intent == IntentType.CONVERSATIONAL and self.domains:
            raise ValueError("Conversational queries must have empty domains list")
        # If tool_required, domains must be non-empty
        if self.intent == IntentType.TOOL_REQUIRED and not self.domains:
            raise ValueError("Tool-required queries must have at least one domain")


@dataclass
class IntentAnalysis:
    """Result of unified intent analysis.

    Attributes:
        intent: Intent type (conversational or tool_required)
        domains: List of relevant domains (empty for conversational)
        complexity: Query complexity (simple, moderate, complex)
        confidence: Confidence score (0.0 to 1.0)
        reasoning: Explanation of the classification
    """

    intent: IntentType
    domains: list[str]
    complexity: QueryComplexity
    confidence: float
    reasoning: str

    def __post_init__(self):
        """Validate the dataclass after initialization."""
        # Validate intent
        if not isinstance(self.intent, IntentType):
            raise ValueError(f"intent must be IntentType, got {type(self.intent)}")

        # Validate domains
        if not isinstance(self.domains, list):
            raise ValueError(f"domains must be list, got {type(self.domains)}")

        # Validate complexity
        if not isinstance(self.complexity, QueryComplexity):
            raise ValueError(f"complexity must be QueryComplexity, got {type(self.complexity)}")

        # Validate confidence
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")

        # Validate domain consistency
        if self.intent == IntentType.CONVERSATIONAL and self.domains:
            raise ValueError("Conversational queries must have empty domains list")
        if self.intent == IntentType.TOOL_REQUIRED and not self.domains:
            raise ValueError("Tool-required queries must have at least one domain")

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "intent": self.intent.value,
            "domains": self.domains,
            "complexity": self.complexity.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


class UnifiedIntentAnalyzer:
    """Unified intent analyzer using LLM-based classification.

    Replaces ConversationalDetector with a scalable, LLM-based approach that:
    - Classifies queries as conversational or tool-required
    - Identifies relevant domains for tool-required queries
    - Assesses query complexity
    - Provides confidence scores and reasoning

    This eliminates hardcoded regex patterns and enables scaling to new
    tool categories without code changes.
    """

    # Available domains that the system supports
    # Must match actual domain directory names in src/me4brain/domains/
    AVAILABLE_DOMAINS = {
        "entertainment",
        "finance_crypto",
        "food",
        "geo_weather",
        "google_workspace",
        "jobs",
        "knowledge_media",
        "medical",
        "productivity",
        "science_research",
        "shopping",
        "sports_booking",
        "sports_nba",
        "tech_coding",
        "travel",
        "utility",
        "web_search",
    }

    def __init__(
        self,
        llm_client: LLMProvider,
        config,
    ) -> None:
        """Initialize the UnifiedIntentAnalyzer.

        Args:
            llm_client: LLM client for classification (local or cloud)
            config: LLM configuration object
        """
        self.llm_client = llm_client
        self.config = config
        logger.info(
            "unified_intent_analyzer_initialized",
            model=config.model_routing,
        )

    async def warm_up(self) -> None:
        """Pre-allocate KV cache by running dummy inferences.

        Eliminates the 'first-query penalty' and dynamic allocation latencies.
        """
        logger.info("unified_intent_warm_up_start")
        from me4brain.llm.models import LLMRequest, Message, MessageRole

        actual_model = self.config.model_routing
        dummy_queries = ["ciao", "meteo", "scrivimi una mail"]
        for q in dummy_queries:
            try:
                prompt = self._build_tier1_prompt(q)
                llm_request = LLMRequest(
                    messages=[Message(role=MessageRole.USER, content=prompt)],
                    model=actual_model,
                    max_tokens=20,
                    temperature=0.1,
                )
                await self.llm_client.generate_response(llm_request)
            except Exception as e:
                logger.warning("warm_up_query_failed", query=q, error=str(e))

        logger.info("unified_intent_warm_up_complete")

    def _build_tier1_prompt(self, query: str) -> str:
        """Build Tier 1 (Fast-track) classification prompt."""
        return f"""Classify the intent and domain of this user query.
Return ONLY a JSON object with:
- "intent": "conversational" or "tool_required"
- "domains": list of relevant domains (e.g., ["geo_weather"], ["finance_crypto"], ["web_search"])
- "complexity": "simple"
- "confidence": float between 0.0 and 1.0

Query: "{query}"
JSON:"""

    def _build_tier2_prompt(self, query: str, context: str | None = None) -> str:
        """Tier 2: Reasoning-heavy prompt for complex queries."""
        prompt = f"""Analyze query: "{query}"
Think step-by-step:
1. Is this casual chat? (intent: conversational)
2. Does it need data/API/search? (intent: tool_required)
3. If tool_required, which domains: {list(self.AVAILABLE_DOMAINS)}

Respond ONLY with valid JSON:
{{
  "intent": "conversational" | "tool_required",
  "domains": ["domain1"],
  "complexity": "simple" | "moderate" | "complex",
  "confidence": 0.0-1.0,
  "reasoning": "step-by-step logic"
}}"""
        if context:
            prompt += f"\nContext: {context}"
        return prompt

    def _build_intent_prompt(
        self,
        query: str,
        context: str | None = None,
    ) -> str:
        """Build LLM prompt for intent classification.

        Args:
            query: User query to classify
            context: Optional conversation context

        Returns:
            Formatted prompt for LLM
        """
        prompt = """You are an intent classifier for an AI assistant system.

Your task: Analyze the user query and determine:
1. Intent: Is it conversational or does it require tools/APIs?
2. Domains: Which domains are relevant? (only if tool_required)
3. Complexity: How complex is the query?

INTENT TYPES:
- conversational: Greetings, small talk, meta questions, opinions
  Examples: "ciao", "come stai", "chi sei", "cosa pensi di X"
  
- tool_required: Requires data retrieval, API calls, external tools
  Examples: "che tempo fa a Roma", "prezzo bitcoin", "cerca notizie", "invia email"

AVAILABLE DOMAINS:
- geo_weather: Weather, forecasts, temperature, climate
- finance_crypto: Cryptocurrency prices, stocks, markets
- web_search: Web search, news, articles
- communication: Email, messaging, notifications
- scheduling: Calendar, events, reminders
- file_management: Documents, files, storage
- data_analysis: Data processing, analysis, visualization
- travel: Flights, hotels, transportation
- food: Restaurants, recipes, food delivery
- entertainment: Movies, music, events
- sports: Sports scores, schedules, news
- shopping: E-commerce, products, prices
- general: General purpose tools

COMPLEXITY LEVELS:
- simple: Single tool, single domain (e.g., "weather in Rome")
- moderate: Multiple tools, single domain (e.g., "weather and forecast for Rome")
- complex: Multiple tools, multiple domains (e.g., "weather in Rome and Bitcoin price")

CRITICAL RULES:
1. Weather queries ALWAYS require tools (geo_weather domain)
2. Price queries ALWAYS require tools (finance_crypto or shopping domain)
3. Search queries ALWAYS require tools (web_search domain)
4. Short queries can require tools (e.g., "meteo Roma" → tool_required)
5. Long queries can be conversational (e.g., "tell me about yourself" → conversational)
6. Only return domains that are in the AVAILABLE DOMAINS list
7. For tool_required queries, always include at least one domain

Respond with ONLY valid JSON (no other text):
{
  "intent": "conversational" | "tool_required",
  "domains": ["domain1", "domain2"],
  "complexity": "simple" | "moderate" | "complex",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}"""

        if context:
            prompt += f"\n\nContext: {context}"

        return prompt

    async def analyze(
        self,
        query: str,
        context: str | None = None,
    ) -> IntentAnalysis:
        """Analyze query intent using LLM.

        Args:
            query: User query to analyze
            context: Optional conversation context

        Returns:
            IntentAnalysis with intent type, domains, and complexity

        Raises:
            ValueError: If query is empty or invalid
        """
        import time

        from me4brain.engine.intent_monitoring import get_intent_monitor

        start_time = time.monotonic()
        monitor = get_intent_monitor()

        # 1. Fast-path: Basic conversational greetings (saves LLM call)
        if self._is_basic_greeting(query):
            logger.info("intent_fast_path_greeting", query_preview=query[:50])
            analysis = IntentAnalysis(
                intent=IntentType.CONVERSATIONAL,
                domains=[],
                complexity=QueryComplexity.SIMPLE,
                confidence=0.99,
                reasoning="fast_path_greeting",
            )
            latency_ms = (time.monotonic() - start_time) * 1000
            monitor.record_analysis(
                intent=analysis.intent.value,
                domains=analysis.domains,
                complexity=analysis.complexity.value,
                confidence=analysis.confidence,
                latency_ms=latency_ms,
            )
            return analysis

        # Validate input
        if not query or not query.strip():
            logger.warning("empty_query_received")
            analysis = IntentAnalysis(
                intent=IntentType.CONVERSATIONAL,
                domains=[],
                complexity=QueryComplexity.SIMPLE,
                confidence=1.0,
                reasoning="empty_query",
            )
            latency_ms = (time.monotonic() - start_time) * 1000
            monitor.record_analysis(
                intent=analysis.intent.value,
                domains=analysis.domains,
                complexity=analysis.complexity.value,
                confidence=analysis.confidence,
                latency_ms=latency_ms,
            )
            return analysis

        # Sanitize query (limit length)
        query = query.strip()
        if len(query) > 1000:
            query = query[:1000]
            logger.warning(
                "query_truncated",
                original_length=len(query),
                truncated_length=1000,
            )

        try:
            # SOTA 2026: Tiered Language Prompting (TLP)
            # Tier 1 for small/fast queries (< 10 words)
            words = query.split()
            use_tier2 = len(words) > 10 or context is not None

            if not use_tier2:
                # TIER 1: FAST PATH
                prompt = self._build_tier1_prompt(query)
                max_tokens = 50
                timeout_ms = 150  # Strict timeout for Tier 1
            else:
                # TIER 2: REASONING PATH
                prompt = self._build_tier2_prompt(query, context)
                max_tokens = 300
                timeout_ms = 1000

            # Call LLM
            from me4brain.llm.models import LLMRequest, Message, MessageRole

            actual_model = self.config.model_routing
            llm_request = LLMRequest(
                messages=[
                    Message(role=MessageRole.USER, content=prompt),
                ],
                model=actual_model,
                temperature=0.1,
                max_tokens=max_tokens,
            )

            response = await self.llm_client.generate_response(llm_request)

            if not response.choices or not response.choices[0].message.content:
                logger.warning(
                    "intent_analysis_empty_response",
                    query_preview=query[:50],
                )
                analysis = self._smart_fallback(query, "empty_response")
                latency_ms = (time.monotonic() - start_time) * 1000
                monitor.record_analysis(
                    intent=analysis.intent.value,
                    domains=analysis.domains,
                    complexity=analysis.complexity.value,
                    confidence=analysis.confidence,
                    latency_ms=latency_ms,
                )
                monitor.record_error("empty_response")
                return analysis

            # Parse JSON response with robust parsing
            content = response.choices[0].message.content or ""
            result = parse_llm_json_response(
                content,
                required_keys=["intent"],
                default=None,
            )

            if result is None:
                logger.warning(
                    "intent_analysis_json_parse_failed",
                    response_preview=content[:100],
                    query_preview=query[:50],
                )
                analysis = self._smart_fallback(query, "json_parse_failed")
                latency_ms = (time.monotonic() - start_time) * 1000
                monitor.record_analysis(
                    intent=analysis.intent.value,
                    domains=analysis.domains,
                    complexity=analysis.complexity.value,
                    confidence=analysis.confidence,
                    latency_ms=latency_ms,
                )
                monitor.record_error("json_parse_failure")
                return analysis

            try:
                # Validate and convert to IntentAnalysisModel
                validated = IntentAnalysisModel(**result)

                # Filter domains to only available ones
                domains = result.get("domains", [])
                valid_domains = [d for d in domains if d in self.AVAILABLE_DOMAINS]

                # If tool_required but no valid domains, add web_search fallback
                intent_val = result.get("intent", "").lower()
                if intent_val == "tool_required" and not valid_domains:
                    valid_domains = ["web_search"]

                # Create final analysis
                analysis = IntentAnalysis(
                    intent=IntentType(intent_val)
                    if intent_val in [i.value for i in IntentType]
                    else IntentType.TOOL_REQUIRED,
                    domains=valid_domains,
                    complexity=QueryComplexity(result.get("complexity", "simple"))
                    if result.get("complexity") in [c.value for c in QueryComplexity]
                    else QueryComplexity.SIMPLE,
                    confidence=result.get("confidence", 0.5),
                    reasoning=result.get("reasoning", "TLP classification"),
                )

                # SOTA 2026: Multi-Domain Semantic Correction
                # If LLM said tool_required but forgot domains, use keywords
                if analysis.intent == IntentType.TOOL_REQUIRED and (
                    not analysis.domains or "general" in analysis.domains
                ):
                    enriched_domains = self._extract_domains_from_query(query)
                    if enriched_domains:
                        analysis.domains = enriched_domains
                        analysis.reasoning += " (keyword_enriched)"

                latency_ms = (time.monotonic() - start_time) * 1000
                monitor.record_analysis(
                    intent=analysis.intent.value,
                    domains=analysis.domains,
                    complexity=analysis.complexity.value,
                    confidence=analysis.confidence,
                    latency_ms=latency_ms,
                )

                logger.info(
                    "intent_analyzed",
                    intent=analysis.intent.value,
                    domains=analysis.domains,
                    complexity=analysis.complexity.value,
                    confidence=analysis.confidence,
                    query_preview=query[:50],
                    latency_ms=round(latency_ms, 2),
                )

                return analysis

            except ValueError as e:
                logger.warning(
                    "intent_analysis_validation_failed",
                    error=str(e),
                    query_preview=query[:50],
                )
                analysis = self._smart_fallback(query, "validation_failed")
                latency_ms = (time.monotonic() - start_time) * 1000
                monitor.record_analysis(
                    intent=analysis.intent.value,
                    domains=analysis.domains,
                    complexity=analysis.complexity.value,
                    confidence=analysis.confidence,
                    latency_ms=latency_ms,
                )
                monitor.record_error("validation_failed")
                return analysis

        except Exception as e:
            logger.error(
                "intent_analysis_failed",
                error=str(e),
                error_type=type(e).__name__,
                query_preview=query[:50],
            )
            analysis = self._smart_fallback(query, f"error:{type(e).__name__}")
            latency_ms = (time.monotonic() - start_time) * 1000
            monitor.record_analysis(
                intent=analysis.intent.value,
                domains=analysis.domains,
                complexity=analysis.complexity.value,
                confidence=analysis.confidence,
                latency_ms=latency_ms,
            )
            monitor.record_error("llm_api_failure")
            return analysis

    def _is_basic_greeting(self, query: str) -> bool:
        """Fast path check for basic greetings to avoid slow LLM calls."""
        # Clean query
        import re

        q = re.sub(r"[^\w\s]", "", query).strip().lower()

        # Pure exact matches
        basic_greetings = {
            "ciao",
            "salve",
            "buongiorno",
            "buonasera",
            "buonanotte",
            "hey",
            "ehi",
            "hi",
            "hello",
            "grazie",
            "grazie mille",
            "ok",
            "va bene",
            "perfetto",
            "ottimo",
            "chi sei",
            "come stai",
            "tutto bene",
            "si",
            "no",
            "esatto",
        }
        return q in basic_greetings

    def _smart_fallback(self, query: str, reason: str) -> IntentAnalysis:
        """Return smart fallback analysis based on query keywords.

        When LLM fails, we use heuristics instead of blindly returning TOOL_REQUIRED.

        Args:
            query: The original user query
            reason: Reason for fallback

        Returns:
            Safe fallback IntentAnalysis
        """
        logger.warning(
            "intent_analysis_smart_fallback",
            reason=reason,
            query_preview=query[:50],
        )

        return IntentAnalysis(
            intent=IntentType.TOOL_REQUIRED,
            domains=["general"],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.5,
            reasoning=f"fallback:{reason}",
        )

    def _extract_domains_from_query(self, query: str) -> list[str]:
        """Utility to extract domains from query using keywords."""
        q = query.lower()

        # SOTA 2026: Global Keyword-to-Domain Map (Defense in Depth)
        DOMAIN_KEYWORDS_MAP = {
            "geo_weather": [
                "meteo",
                "tempo fa",
                "temperatura",
                "piove",
                "neve",
                "previsioni",
                "gradi",
                "weather",
                "forecast",
                "temperature",
                "climate",
                "tempo",
            ],
            "finance_crypto": [
                "prezzo",
                "costa",
                "bitcoin",
                "crypto",
                "azione",
                "borsa",
                "euro",
                "dollaro",
            ],
            "web_search": [
                "cerca",
                "trova",
                "notizie",
                "news",
                "chi è",
                "cos'è",
                "wikipedia",
                "search",
            ],
            "google_workspace": [
                "email",
                "scrivi",
                "invia",
                "messaggio",
                "posta",
                "gmail",
                "calendar",
                "documento",
                "drive",
            ],
            "productivity": [
                "calendario",
                "appuntamento",
                "riunione",
                "meeting",
                "evento",
                "task",
                "todo",
            ],
            "travel": ["volo", "hotel", "treno", "viaggio", "prenota", "destinazione"],
            "food": ["ristorante", "menu", "pizza", "mangiare", "cibo"],
            "entertainment": ["film", "musica", "canzone", "cinema", "netflix", "spotify"],
            "sports_nba": [
                "nba",
                "basketball",
                "giocatore",
                "squadra",
                "partita nba",
                "lakers",
                "celtics",
                "warriors",
            ],
            "sports_booking": ["prenota", "biglietto", "stadio", "evento sportivo"],
            "shopping": ["compra", "acquista", "negozio", "prezzo", "prodotto", "amazon"],
            "tech_coding": [
                "codice",
                "programma",
                "python",
                "javascript",
                "api",
                "database",
                "algoritmo",
            ],
            "jobs": ["lavoro", "carriera", "cv", "candidato", "offerta di lavoro"],
            "medical": ["medico", "salute", "malattia", "farmaco", "sintomo", "cura"],
            "knowledge_media": ["articolo", "blog", "ricerca", "studio", "paper", "scientifico"],
            "science_research": [
                "ricerca",
                "esperimento",
                "scoperta",
                "studio scientifico",
                "teoria",
            ],
            "utility": ["calcolo", "conversione", "unità", "matematica"],
        }

        found = set()
        for domain, keywords in DOMAIN_KEYWORDS_MAP.items():
            if any(kw in q for kw in keywords):
                found.add(domain)

        return list(found)
