"""Stage 1: Domain Classification.

Classifies user queries into relevant domains with estimated complexity.
Uses a lightweight LLM call to determine which tool domains are needed.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from me4brain.cache.cache_manager import CacheManager

from me4brain.engine.hybrid_router.metrics import (
    CACHE_HITS,
    CACHE_MISSES,
    CLASSIFICATION_CONFIDENCE,
    CLASSIFICATION_LATENCY,
    CLASSIFICATION_RETRIES,
    CLASSIFICATION_TOTAL,
    LLM_ERRORS,
    QUERY_WITH_CONTEXT,
)
from me4brain.engine.hybrid_router.trace_contract import (
    FallbackType,
    StageTrace,
    StageType,
)
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainComplexity,
    HybridRouterConfig,
)
from me4brain.llm.nanogpt import NanoGPTClient
from me4brain.utils.json_utils import robust_json_parse

logger = structlog.get_logger(__name__)

# Domain classification timeout (30 seconds for local models)
DOMAIN_CLASSIFICATION_TIMEOUT = 30  # Reduced from 600 for better debugging
MAX_CLASSIFICATION_RETRIES = 3  # Retry before fallback


class DegradationLevel(Enum):
    """Graceful degradation levels for domain classification.

    Allows graduated failure handling instead of binary success/fallback:
    - FULL_LLM: Complete LLM-based classification (normal operation)
    - SIMPLIFIED_LLM: Simplified LLM prompt (complex prompt failed)
    - HYBRID: LLM confidence + keyword backup (LLM uncertain)
    - KEYWORD_ONLY: Pure keyword-based fallback (last resort)
    """

    FULL_LLM = 0
    SIMPLIFIED_LLM = 1
    HYBRID = 2
    KEYWORD_ONLY = 3


class DomainClassifier:
    """Classifies queries into relevant domains.

    Stage 1 of the hybrid router - determines which domains are relevant
    for a query before selecting specific tools.

    Features optional caching via Redis with semantic similarity matching.
    """

    def __init__(
        self,
        llm_client: NanoGPTClient,
        available_domains: list[str],
        config: HybridRouterConfig | None = None,
        cache_manager: CacheManager | None = None,
    ) -> None:
        self._llm = llm_client
        self._domains = available_domains
        self._config = config or HybridRouterConfig()
        self._cache_manager = cache_manager

    @property
    def cache_manager(self) -> CacheManager | None:
        """Get the cache manager (lazy initialization)."""
        return self._cache_manager

    def set_cache_manager(self, cache_manager: CacheManager) -> None:
        """Set the cache manager.

        Args:
            cache_manager: CacheManager instance for caching classification results
        """
        self._cache_manager = cache_manager

    async def _check_cache(
        self,
        query: str,
        user_content: str,
    ) -> DomainClassification | None:
        """Check if query result is cached.

        Args:
            query: Original user query
            user_content: Built user content (for cache key generation)

        Returns:
            Cached DomainClassification if found, None otherwise
        """
        if self._cache_manager is None:
            return None

        try:
            from me4brain.cache.query_normalizer import generate_cache_key

            # Generate cache key
            model = self._config.router_model
            provider = getattr(self._llm, "provider", "unknown")
            cache_key = generate_cache_key(query, model, provider)

            # Try to get from cache
            cached_response = await self._cache_manager.get(cache_key)
            if cached_response is None:
                # Cache miss
                model_label = model or "unknown"
                provider_label = provider or "unknown"
                CACHE_MISSES.labels(model=model_label, provider=provider_label).inc()
                return None

            # Convert to DomainClassification
            classification = cached_response.to_domain_classification()

            # Record cache hit
            model_label = model or "unknown"
            provider_label = provider or "unknown"
            CACHE_HITS.labels(model=model_label, provider=provider_label).inc()

            # Update hit ratio (simplified - actual ratio would need proper tracking)
            logger.debug(
                "cache_hit_recorded",
                key=cache_key,
                domains=classification.domain_names,
            )

            return classification

        except Exception as e:
            logger.warning("cache_check_failed", error=str(e))
            return None

    async def _cache_result(
        self,
        query: str,
        classification: DomainClassification,
        method: str,
    ) -> None:
        """Cache a classification result.

        Args:
            query: Original user query
            classification: DomainClassification to cache
            method: Classification method ('llm', 'fallback_keyword', etc.)
        """
        if self._cache_manager is None:
            return

        try:
            from me4brain.cache.cache_manager import CachedResponse
            from me4brain.cache.query_normalizer import generate_cache_key

            # Generate cache key
            model = self._config.router_model
            provider = getattr(self._llm, "provider", "unknown")
            cache_key = generate_cache_key(query, model, provider)

            # Serialize domains
            domains_data = [
                {"name": d.name, "complexity": d.complexity} for d in classification.domains
            ]

            # Create cached response
            # Use first domain as primary for backwards compatibility
            primary_domain = classification.domains[0].name if classification.domains else "unknown"
            cached_response = CachedResponse(
                domain=primary_domain,
                domains=domains_data,
                confidence=classification.confidence,
                query_summary=classification.query_summary,
                method=method,
                cached_at=time.time(),
            )

            # Cache with default TTL (1 hour)
            from me4brain.config.cache_config import get_cache_settings

            settings = get_cache_settings()
            await self._cache_manager.set(cache_key, cached_response, ttl=settings.default_ttl)

            logger.debug(
                "classification_cached",
                key=cache_key,
                domains=classification.domain_names,
                ttl=settings.default_ttl,
            )

        except Exception as e:
            logger.warning("cache_write_failed", error=str(e))

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

    def _build_simplified_router_prompt(self, current_datetime: str) -> str:
        """Build a simplified system prompt for domain classification.

        Used during degradation when the full prompt failed.
        Removes complex examples and focuses on core task.
        """
        domain_list = ", ".join([f'"{d}"' for d in self._domains])

        return f"""You are a DOMAIN CLASSIFIER. Analyze the user query and identify relevant domains.

## TASK
Determine which domains (tool categories) are relevant for the query.

## DOMAINS
{domain_list}

## COMPLEXITY
- "low": 1-3 tools
- "medium": 4-8 tools  
- "high": 8+ tools or complex

## OUTPUT
Return JSON with: domains (list of {{name, complexity}}), confidence (0-1), query_summary (brief string)

## KEY RULES
- "sports_nba" for basketball, NBA, betting, odds, predictions
- "finance_crypto" for stocks, crypto, trading
- "geo_weather" for weather, temperature, climate
- "google_workspace" for Gmail, Calendar, Drive, Docs, Sheets
- "web_search" for information, news, research

Current time: {current_datetime}"""

    async def classify(
        self,
        query: str,
        conversation_context: list[dict[str, Any]] | None = None,
        intent_analysis: dict[str, Any] | None = None,
        simplified: bool = False,
    ) -> DomainClassification:
        """Classify a query into relevant domains.

        Args:
            query: User query to classify
            conversation_context: Recent conversation history for context
            intent_analysis: Optional pre-analysis from IntentAnalyzer
            simplified: If True, use simplified prompt without complex examples

        Returns:
            DomainClassification with domains, complexity, and confidence
        """
        from me4brain.llm.models import LLMRequest, Message, MessageRole

        start_time = time.time()
        has_context = conversation_context is not None and len(conversation_context) > 0
        QUERY_WITH_CONTEXT.labels(has_context=str(has_context)).inc()

        current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Use simplified prompt if degradation is in progress
        if simplified:
            system_prompt = self._build_simplified_router_prompt(current_dt)
        else:
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

        # Check cache before LLM call (only for non-simplified queries)
        if self._cache_manager is not None and not simplified:
            cached = await self._check_cache(query, user_content)
            if cached is not None:
                elapsed = time.time() - start_time
                CLASSIFICATION_LATENCY.labels(method="cache").observe(elapsed)
                logger.info(
                    "domain_classification_cache_hit",
                    query_preview=query[:50],
                    domains=cached.domain_names,
                    confidence=cached.confidence,
                    latency_seconds=elapsed,
                )
                return cached

        # Retry loop with exponential backoff before falling back
        last_error = None
        for attempt in range(1, MAX_CLASSIFICATION_RETRIES + 1):
            try:
                # Wrap LLM call with timeout protection (30 seconds for local models)
                try:
                    response = await asyncio.wait_for(
                        self._llm.generate_response(request),
                        timeout=DOMAIN_CLASSIFICATION_TIMEOUT,
                    )
                except TimeoutError as e:
                    last_error = e
                    CLASSIFICATION_RETRIES.labels(reason="timeout").inc()
                    LLM_ERRORS.labels(error_type="timeout").inc()
                    logger.warning(
                        "domain_classification_timeout",
                        attempt=attempt,
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        timeout_seconds=DOMAIN_CLASSIFICATION_TIMEOUT,
                        query_preview=query[:50],
                    )
                    if attempt < MAX_CLASSIFICATION_RETRIES:
                        # Exponential backoff: 0.5s, 1.0s, 1.5s
                        backoff_delay = 0.5 * attempt
                        await asyncio.sleep(backoff_delay)
                        continue
                    raise

                content = response.choices[0].message.content or ""
                content = content.strip()

                logger.debug(
                    "domain_classification_raw_output",
                    attempt=attempt,
                    content=content,
                )

                # Add JSON recovery for partial/multi-line responses
                # This helps if the LLM response is incomplete or has whitespace issues
                if not content:
                    last_error = ValueError("Empty response from LLM")
                    logger.warning(
                        "domain_classification_empty_response",
                        attempt=attempt,
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        query_preview=query[:50],
                    )
                    if attempt < MAX_CLASSIFICATION_RETRIES:
                        backoff_delay = 0.5 * attempt
                        await asyncio.sleep(backoff_delay)
                        continue
                    raise last_error

                data = robust_json_parse(content, expect_object=True)

                if not data or not isinstance(data, dict):
                    last_error = ValueError("Failed to parse JSON from LLM response")
                    logger.warning(
                        "domain_classification_json_error",
                        attempt=attempt,
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        query_preview=query[:50],
                        content_preview=content[:100],
                    )
                    if attempt < MAX_CLASSIFICATION_RETRIES:
                        backoff_delay = 0.5 * attempt
                        await asyncio.sleep(backoff_delay)
                        continue
                    raise last_error

                try:
                    # Type is now guaranteed to be dict[str, Any]
                    data_dict: dict[str, Any] = data  # type: ignore[assignment]
                    domains = []
                    for d in data_dict.get("domains", []):
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
                        confidence=data_dict.get("confidence", 0.8),
                        query_summary=data_dict.get("query_summary", ""),
                    )

                    # Record metrics for successful LLM classification
                    elapsed = time.time() - start_time
                    CLASSIFICATION_LATENCY.labels(method="llm").observe(elapsed)
                    CLASSIFICATION_TOTAL.labels(method="llm", success="true").inc()
                    CLASSIFICATION_CONFIDENCE.labels(method="llm").observe(
                        classification.confidence
                    )

                    logger.info(
                        "domain_classification_llm_success",
                        attempt=attempt,
                        query_preview=query[:50],
                        domains=[d.name for d in domains],
                        confidence=classification.confidence,
                        is_multi_domain=classification.is_multi_domain,
                        latency_seconds=elapsed,
                    )

                    # Cache the result (only on successful LLM classification)
                    if self._cache_manager is not None:
                        await self._cache_result(query, classification, "llm")

                    return classification

                except Exception as e:
                    last_error = e
                    logger.warning(
                        "domain_classification_parse_error",
                        attempt=attempt,
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        error=str(e),
                        query_preview=query[:50],
                    )
                    if attempt < MAX_CLASSIFICATION_RETRIES:
                        backoff_delay = 0.5 * attempt
                        await asyncio.sleep(backoff_delay)
                        continue
                    raise

            except Exception as e:
                last_error = e
                if attempt == MAX_CLASSIFICATION_RETRIES:
                    # All retries exhausted - fall back
                    elapsed = time.time() - start_time
                    CLASSIFICATION_TOTAL.labels(method="fallback_keyword", success="false").inc()
                    CLASSIFICATION_LATENCY.labels(method="fallback_keyword").observe(elapsed)
                    LLM_ERRORS.labels(error_type="parse").inc()

                    logger.warning(
                        "domain_classification_fallback",
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        last_error=str(e),
                        query_preview=query[:50],
                        latency_seconds=elapsed,
                    )
                    return self._fallback_classification(query)
                # Continue to next retry
                continue

        # Should not reach here, but ensure fallback
        logger.error(
            "domain_classification_failed",
            error=str(last_error),
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

        # Retry loop with exponential backoff before falling back
        last_error: Exception | None = None
        for attempt in range(1, MAX_CLASSIFICATION_RETRIES + 1):
            try:
                # Wrap LLM call with timeout protection
                try:
                    response = await asyncio.wait_for(
                        self._llm.generate_response(request),
                        timeout=DOMAIN_CLASSIFICATION_TIMEOUT,
                    )
                    trace.provider_resolved = getattr(self._llm, "provider", "unknown")
                    trace.model_effective = self._config.router_model

                except TimeoutError as e:
                    last_error = e
                    logger.warning(
                        "domain_classification_timeout",
                        attempt=attempt,
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        timeout_seconds=DOMAIN_CLASSIFICATION_TIMEOUT,
                        query_preview=query[:50],
                    )
                    if attempt < MAX_CLASSIFICATION_RETRIES:
                        backoff_delay = 0.5 * attempt
                        await asyncio.sleep(backoff_delay)
                        continue

                    # All retries exhausted
                    trace.fallback_applied = True
                    trace.fallback_type = FallbackType.LLM_TIMEOUT
                    trace.fallback_reason = f"Domain classification LLM timeout after {MAX_CLASSIFICATION_RETRIES} attempts"
                    trace.success = False
                    trace.error_code = "TIMEOUT"
                    trace.error_message = f"LLM timeout after {DOMAIN_CLASSIFICATION_TIMEOUT}s"
                    trace.duration_ms = (time.time() - start_time) * 1000

                    classification = self._fallback_classification(query)
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence
                    trace.used_fallback_keywords = True
                    return classification, trace

                content = response.choices[0].message.content or ""
                content = content.strip()

                logger.debug(
                    "domain_classification_raw_output",
                    attempt=attempt,
                    content=content,
                )

                # Handle empty response
                if not content:
                    last_error = ValueError("Empty response from LLM")
                    logger.warning(
                        "domain_classification_empty_response",
                        attempt=attempt,
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        query_preview=query[:50],
                    )
                    if attempt < MAX_CLASSIFICATION_RETRIES:
                        backoff_delay = 0.5 * attempt
                        await asyncio.sleep(backoff_delay)
                        continue

                    # All retries exhausted
                    trace.fallback_applied = True
                    trace.fallback_type = FallbackType.LLM_PARSE_ERROR
                    trace.fallback_reason = "Empty LLM response after all retries"
                    trace.success = False
                    trace.error_code = "EMPTY_RESPONSE"
                    trace.error_message = "LLM returned empty content"
                    trace.duration_ms = (time.time() - start_time) * 1000

                    classification = self._fallback_classification(query)
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence
                    trace.used_fallback_keywords = True
                    return classification, trace

                # Parse JSON
                data = robust_json_parse(content, expect_object=True)

                if not data or not isinstance(data, dict):
                    last_error = ValueError("Failed to parse JSON from LLM response")
                    logger.warning(
                        "domain_classification_json_error",
                        attempt=attempt,
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        query_preview=query[:50],
                        content_preview=content[:100],
                    )
                    if attempt < MAX_CLASSIFICATION_RETRIES:
                        backoff_delay = 0.5 * attempt
                        await asyncio.sleep(backoff_delay)
                        continue

                    # All retries exhausted
                    trace.fallback_applied = True
                    trace.fallback_type = FallbackType.LLM_PARSE_ERROR
                    trace.fallback_reason = "JSON parse failed after all retries"
                    trace.success = False
                    trace.error_code = "JSON_PARSE_ERROR"
                    trace.error_message = f"Failed to parse JSON from: {content[:100]}"
                    trace.duration_ms = (time.time() - start_time) * 1000

                    classification = self._fallback_classification(query)
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence
                    trace.used_fallback_keywords = True
                    return classification, trace

                try:
                    # Type is now guaranteed to be dict[str, Any]
                    data_dict: dict[str, Any] = data  # type: ignore[assignment]
                    domains = []
                    for d in data_dict.get("domains", []):
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
                        confidence=data_dict.get("confidence", 0.8),
                        query_summary=data_dict.get("query_summary", ""),
                    )

                    # Trace success
                    trace.success = True
                    trace.fallback_applied = False
                    trace.fallback_type = FallbackType.NONE
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence

                    logger.info(
                        "domain_classification_llm_success",
                        attempt=attempt,
                        query_preview=query[:50],
                        domains=[d.name for d in domains],
                        confidence=classification.confidence,
                        is_multi_domain=classification.is_multi_domain,
                    )

                    trace.duration_ms = (time.time() - start_time) * 1000
                    return classification, trace

                except Exception as e:
                    last_error = e
                    logger.warning(
                        "domain_classification_parse_error",
                        attempt=attempt,
                        max_attempts=MAX_CLASSIFICATION_RETRIES,
                        error=str(e),
                        query_preview=query[:50],
                    )
                    if attempt < MAX_CLASSIFICATION_RETRIES:
                        backoff_delay = 0.5 * attempt
                        await asyncio.sleep(backoff_delay)
                        continue

                    # All retries exhausted
                    trace.fallback_applied = True
                    trace.fallback_type = FallbackType.LLM_PARSE_ERROR
                    trace.fallback_reason = (
                        f"Classification parse error after all retries: {str(e)}"
                    )
                    trace.success = False
                    trace.error_code = "PARSE_ERROR"
                    trace.error_message = str(e)
                    trace.duration_ms = (time.time() - start_time) * 1000

                    classification = self._fallback_classification(query)
                    trace.output_domains = classification.domain_names
                    trace.output_count = len(classification.domain_names)
                    trace.confidence_score = classification.confidence
                    trace.used_fallback_keywords = True
                    return classification, trace

            except Exception as e:
                last_error = e
                if attempt == MAX_CLASSIFICATION_RETRIES:
                    # All retries exhausted
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
                continue

        # Should not reach here, but ensure fallback
        logger.error(
            "domain_classification_failed",
            error=str(last_error),
            query_preview=query[:50],
        )
        trace.fallback_applied = True
        trace.fallback_type = FallbackType.LLM_EXCEPTION
        trace.fallback_reason = "Exhausted all retries"
        trace.success = False
        trace.error_code = "EXCEPTION"
        trace.error_message = "All retries exhausted"
        trace.duration_ms = (time.time() - start_time) * 1000

        classification = self._fallback_classification(query)
        trace.output_domains = classification.domain_names
        trace.output_count = len(classification.domain_names)
        trace.confidence_score = classification.confidence
        trace.used_fallback_keywords = True
        return classification, trace

    def _get_keyword_map(self) -> dict[str, list[str]]:
        """Get keyword map for domain classification.

        First tries to get keywords from ToolContractRegistry (auto-sync).
        Falls back to hardcoded map if registry is not populated.

        Returns:
            Dictionary mapping domain -> list of keywords
        """
        # ✅ Wave 1.4: Auto-sync keywords from registry
        try:
            from me4brain.engine.tool_contract import ToolContractRegistry

            registry = ToolContractRegistry.get_instance()
            registry_keywords = registry.get_domain_keywords()

            # Check if registry has meaningful keywords (not empty)
            if registry_keywords and any(kw for kw in registry_keywords.values() if kw):
                # Merge registry keywords with fallback map
                merged: dict[str, list[str]] = dict(FALLBACK_KEYWORD_MAP)

                # Add registry keywords, preserving existing entries
                for domain, keywords in registry_keywords.items():
                    if domain in merged:
                        # Add new keywords not already present
                        existing = set(merged[domain])
                        for kw in keywords:
                            if kw.lower() not in [k.lower() for k in existing]:
                                merged[domain].append(kw)
                    else:
                        # New domain from registry
                        merged[domain] = keywords

                self._logger.debug(
                    "keyword_map_synced_from_registry",
                    domains_with_keywords=len(merged),
                )
                return merged

        except Exception as e:
            self._logger.debug(
                "keyword_map_registry_sync_failed",
                error=str(e),
            )

        # Fall back to hardcoded map
        return FALLBACK_KEYWORD_MAP

    def _fallback_classification(self, query: str) -> DomainClassification:
        """Generate fallback classification when LLM fails.

        Uses keyword-based domain detection instead of generic web_search.
        Keywords are auto-synced from ToolContractRegistry when available.
        """
        query_lower = query.lower()
        detected_domains: list[str] = []

        # ✅ Wave 1.4: Use auto-synced keyword map
        keyword_map = self._get_keyword_map()

        for domain, keywords in keyword_map.items():
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

    async def classify_with_degradation(
        self,
        query: str,
        context: list[dict[str, Any]] | None = None,
        max_degradation: DegradationLevel = DegradationLevel.KEYWORD_ONLY,
    ) -> DomainClassification:
        """Classify with graduated degradation levels.

        Attempts classification at progressively degraded levels:
        1. FULL_LLM: Complete prompt with context and examples
        2. SIMPLIFIED_LLM: Simpler prompt without complex examples
        3. HYBRID: LLM confidence score + keyword backup
        4. KEYWORD_ONLY: Pure keyword-based fallback

        Args:
            query: The user query to classify
            context: Optional conversation context
            max_degradation: Maximum degradation level to attempt

        Returns:
            DomainClassification from the first successful level
        """
        logger.info(
            "classify_with_degradation_start",
            query_preview=query[:50],
            max_degradation=max_degradation.name,
        )

        for level in DegradationLevel:
            # Skip levels beyond max_degradation
            if level.value > max_degradation.value:
                break

            try:
                logger.debug(
                    "degradation_level_attempt",
                    level=level.name,
                    attempt_number=level.value + 1,
                )

                result = await self._classify_at_level(query, context, level)

                if result and result.confidence > 0.5:
                    logger.info(
                        "classification_succeeded_at_level",
                        level=level.name,
                        confidence=result.confidence,
                        domains=result.domain_names,
                    )
                    return result

            except Exception as e:
                logger.warning(
                    "classification_level_failed",
                    level=level.name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Continue to next degradation level
                continue

        # If all levels fail or return low confidence, use keyword fallback
        logger.warning(
            "classification_all_levels_failed_using_keyword_fallback",
            query_preview=query[:50],
        )
        return self._fallback_classification(query)

    async def _classify_at_level(
        self,
        query: str,
        context: list[dict[str, Any]] | None = None,
        level: DegradationLevel = DegradationLevel.FULL_LLM,
    ) -> DomainClassification | None:
        """Classify at a specific degradation level.

        Args:
            query: The user query
            context: Optional conversation context
            level: The degradation level to attempt

        Returns:
            DomainClassification if successful, None if it fails
        """
        if level == DegradationLevel.FULL_LLM:
            # Normal classification with full context
            return await self.classify(query, context, None)

        elif level == DegradationLevel.SIMPLIFIED_LLM:
            # Simplified classification with shorter prompt
            return await self.classify(query, context, None, simplified=True)

        elif level == DegradationLevel.HYBRID:
            # LLM tries but keywords provide backup
            llm_result = await self.classify(query, context, None, simplified=True)

            # If LLM confidence is low, enhance with keyword detection
            if llm_result and llm_result.confidence < 0.7:
                keyword_result = self._fallback_classification(query)

                # Combine results: prefer LLM domains but add keyword domains if missing
                combined_domains = list(llm_result.domains)
                existing_names = set(llm_result.domain_names)

                for kw_domain in keyword_result.domains:
                    if kw_domain.name not in existing_names:
                        combined_domains.append(kw_domain)

                return DomainClassification(
                    domains=combined_domains,
                    confidence=min(llm_result.confidence, 0.75),  # Cap at 0.75 for hybrid
                    query_summary=llm_result.query_summary,
                )

            return llm_result

        elif level == DegradationLevel.KEYWORD_ONLY:
            # Pure keyword fallback
            return self._fallback_classification(query)

        return None

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


# ✅ Wave 1.4: Hardcoded fallback keyword map
# This is used when ToolContractRegistry is not populated or fails
# NOTE: This is imported and used by _get_keyword_map() method in DomainClassifier
FALLBACK_KEYWORD_MAP: dict[str, list[str]] = {
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
        # Italian betting keywords
        "scommessa",
        "scommesse",
        "pronostico",
        "pronostici",
        "sistema scommesse",
        "value bet",
        # English betting keywords
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
