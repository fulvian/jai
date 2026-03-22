"""Stage 1b: Query Decomposition.

Decomposes multi-intent queries into atomic sub-queries.
This improves retrieval precision by isolating each intent before embedding.

Universal design: the decomposer adapts dynamically to ANY query type,
generating the right number of sub-queries based on general principles
(depth, dependencies, parallelism, completeness) rather than hard-coded patterns.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from me4brain.llm.nanogpt import NanoGPTClient, LLMRequest

from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    HybridRouterConfig,
    SubQuery,
)
from me4brain.utils.json_utils import robust_json_parse

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Prompt template for query decomposition
# ---------------------------------------------------------------------------
# Design principles:
#   - Teach the LLM HOW to reason about granularity, not WHAT to decompose
#   - Keep examples varied and abstract — never tied to a specific edge case
#   - Use universal rules so the decomposer adapts to any domain/query type
# ---------------------------------------------------------------------------
DECOMPOSITION_SYSTEM_PROMPT = """\
You are a Query Decomposer for a multi-domain tool retrieval system.

Your task is to decompose user queries into ATOMIC sub-queries.
Each sub-query should represent ONE distinct action targeting ONE domain.

## CRITICAL RULES:
1. Each sub-query MUST target exactly ONE domain
2. Preserve all key entities, dates, filters, and context in each sub-query
3. Output ONLY a valid JSON array — no other text

## GRANULARITY PRINCIPLES (apply dynamically to any query):

### Depth Rule
When the user asks to **analyze**, **cross-reference**, **investigate**, or
**produce a report/summary**, the request requires deep exploration.
Break it into phases:
- **Gather**: separate sub-queries for each distinct data source
- **Explore**: if a gather step may return collections (folders, threads,
  lists), add sub-queries to drill into their contents
- **Produce**: if the user requests final output (report, document,
  summary, email), add a sub-query for creation

## IRON RULE FOR google_workspace MULTI-SOURCE QUERIES:
When the user mentions MULTIPLE Google sources (documents/files + emails + calendar + meet):
1. Create EXACTLY ONE sub-query per source API, preserving ALL entities and dates:
   - intent: "drive_search" → search Google Drive
   - intent: "gmail_search" → search Gmail
   - intent: "calendar_search" → search Calendar events
   - intent: "meet_search" → search Meet conferences
2. Each sub-query MUST include the FULL entity context (names, dates, topic)
   BUT keep the sub_query TEXT short and keyword-focused (max 8-10 words).
   The sub_query text is used as a SEARCH QUERY for APIs — long sentences perform poorly.
   Good: "Castelvetere ANCI gestione associata ottobre 2024"
   Bad: "cerca tutti i documenti file relativi al Comune di Castelvetere sul progetto ANCI piccoli di gestione associata dei servizi comunali da ottobre 2024 ad oggi"
3. NEVER create sub-queries for "analyze", "cross-reference", "elaborate report" — synthesis is automatic
4. ONLY create a "content_creation" sub-query if user explicitly asks to SAVE/CREATE a document

### Dependency Rule
When a later action DEPENDS on results from an earlier one (e.g. "read what
you found", "summarize the results"), generate them as SEPARATE sequential
sub-queries. The execution engine automatically passes results forward.

### Parallelism Rule
Independent actions across DIFFERENT data sources should be separate
sub-queries even within the same high-level domain.

### Completeness Rule
If the user lists MULTIPLE sources or entity types explicitly, generate
AT LEAST one sub-query per source. Never merge distinct sources into one.

### Simplicity Rule
For simple, single-intent queries, return a SINGLE sub-query. Do NOT
over-decompose trivial requests.

### Tool-Actionability Rule
Every sub-query MUST correspond to a concrete tool action (search, read, list,
create, get, update, etc.). Do NOT generate sub-queries for pure analysis,
cross-referencing, or summarization — these are automatically handled by the
system's final synthesis step. Only create a "content_creation" sub-query if
the user explicitly asks for an OUTPUT to be CREATED (e.g., "save a report
as Google Doc", "create a spreadsheet").

## Available Domains:
{available_domains}

## Detected Domains for this query:
{detected_domains}

## Examples (varied complexity):

Query: "Che tempo fa a Roma domani?"
Output:
[
  {{"sub_query": "meteo Roma domani", "domain": "geo_weather", "intent": "weather_check"}}
]

Query: "Cerca le email sul contratto e imposta un promemoria per lunedì"
Output:
[
  {{"sub_query": "cerca email relative al contratto", "domain": "google_workspace", "intent": "email_search"}},
  {{"sub_query": "crea promemoria per lunedì", "domain": "productivity", "intent": "reminder_create"}}
]

Query: "Raccogli tutti i documenti, le email e gli appuntamenti relativi al progetto X, poi analizza i contenuti e preparami un riassunto completo"
Output:
[
  {{"sub_query": "cerca file e documenti relativi al progetto X", "domain": "google_workspace", "intent": "file_search"}},
  {{"sub_query": "leggi il contenuto dei documenti trovati sul progetto X", "domain": "google_workspace", "intent": "file_read"}},
  {{"sub_query": "cerca email relative al progetto X", "domain": "google_workspace", "intent": "email_search"}},
  {{"sub_query": "cerca appuntamenti ed eventi relativi al progetto X", "domain": "google_workspace", "intent": "calendar_search"}}
]

Query: "Analizza le partite NBA stasera, individua i migliori pronostici ed elabora un sistema per scommettere"
Output:
[
  {{"sub_query": "recupera partite NBA in programma stasera con quote e statistiche squadre", "domain": "sports_nba", "intent": "nba_games_data"}},
  {{"sub_query": "recupera infortuni e classifiche NBA per le squadre in campo stasera", "domain": "sports_nba", "intent": "nba_context_data"}}
]

Query: "Cerca paper su arXiv riguardo LLM e confrontali con le ultime news tech"
Output:
[
  {{"sub_query": "search papers on arXiv about LLM", "domain": "science_research", "intent": "scientific_search"}},
  {{"sub_query": "search latest news about LLM and tech", "domain": "knowledge_media", "intent": "news_search"}}
]

## CRITICAL DISAMBIGUATION:
- "scommesse", "betting", "pronostico/i", "odds", "value bet", "spread", "over/under" → domain is ALWAYS "sports_nba", NEVER "finance_crypto"
- "finance_crypto" is for stocks, crypto, forex, ETFs, bonds — NOT sports betting
- "google_workspace" is for all G-Suite tools (Drive, Docs, Sheets, Gmail, Calendar, Meet)
- ALL sub-queries about sports betting must use domain "sports_nba" (where nba_betting_analyzer tool lives)

Now decompose the following query:
"""


class QueryDecomposer:
    """Decomposes multi-intent queries into atomic sub-queries.

    Stage 1b of the hybrid router - optional step that runs AFTER domain
    classification and BEFORE tool retrieval for complex multi-intent queries.

    Design: universal and adaptive — the decomposer uses general granularity
    principles to decide how many sub-queries to generate, rather than
    pattern-matching against specific query templates.
    """

    def __init__(
        self,
        llm_client: "NanoGPTClient",
        available_domains: list[str],
        config: HybridRouterConfig | None = None,
    ) -> None:
        """Initialize the query decomposer.

        Args:
            llm_client: NanoGPT client for LLM calls
            available_domains: List of valid domain names
            config: Router configuration
        """
        self._llm = llm_client
        self._available_domains = available_domains
        self._config = config or HybridRouterConfig()

    async def decompose(
        self,
        query: str,
        classification: DomainClassification,
    ) -> list[SubQuery]:
        """Decompose a query into atomic sub-queries.

        Args:
            query: Original user query (potentially multi-intent)
            classification: Domain classification from Stage 1

        Returns:
            List of SubQuery objects, each targeting a single domain.
            For simple single-intent queries, returns a single SubQuery.
        """
        # Optimization: skip decomposition for simple queries
        if not self.should_decompose(query, classification):
            logger.debug(
                "query_decomposition_skipped",
                reason="simple_query",
                word_count=len(query.split()),
            )
            return [
                SubQuery(
                    text=query,
                    domain=classification.domain_names[0]
                    if classification.domain_names
                    else "web_search",
                    intent="direct",
                )
            ]

        # Build decomposition prompt
        system_prompt = DECOMPOSITION_SYSTEM_PROMPT.format(
            available_domains=", ".join(self._available_domains),
            detected_domains=", ".join(classification.domain_names),
        )

        user_prompt = f"Query: {query}"

        try:
            from me4brain.llm.models import LLMRequest, Message, MessageRole

            # Wrap LLM call with timeout protection (60 seconds)
            # This prevents hanging on complex decomposition tasks
            try:
                # B2 FIX: Use decomposition_model instead of router_model
                model_to_use = self._config.decomposition_model
                response = await asyncio.wait_for(
                    self._llm.generate_response(
                        LLMRequest(
                            messages=[
                                Message(role=MessageRole.SYSTEM, content=system_prompt),
                                Message(role=MessageRole.USER, content=user_prompt),
                            ],
                            model=model_to_use,
                            temperature=0.1,  # Low temperature for consistent JSON
                            max_tokens=2000,  # Allow more tokens for complex decompositions
                        )
                    ),
                    timeout=240.0,  # 240 second timeout for decomposition (development)
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "query_decomposition_timeout",
                    timeout_seconds=240,
                    fallback="heuristic_decomposition",
                    query_length=len(query),
                )
                # B3 FIX: Use heuristic fallback instead of raw query
                return self._heuristic_fallback_decomposition(query, classification)

            raw_content = response.choices[0].message.content or ""
            logger.debug("query_decomposition_raw_output", content=raw_content)

            sub_queries = self._parse_decomposition(raw_content, classification)

            logger.info(
                "query_decomposed",
                original_query=query[:80],
                sub_query_count=len(sub_queries),
                domains=[sq.domain for sq in sub_queries],
                intents=[sq.intent for sq in sub_queries],
            )

            return sub_queries

        except Exception as e:
            logger.warning(
                "query_decomposition_failed",
                error=str(e),
                fallback="heuristic_decomposition",
            )
            # B3 FIX: Use heuristic fallback instead of raw query
            return self._heuristic_fallback_decomposition(query, classification)

    def _heuristic_fallback_decomposition(
        self,
        query: str,
        classification: DomainClassification,
    ) -> list[SubQuery]:
        """Heuristic fallback decomposition when LLM fails.
        
        This provides deterministic decomposition for common patterns
        when the LLM is unavailable or fails.
        
        Args:
            query: Original user query
            classification: Domain classification result
            
        Returns:
            List of SubQuery objects based on heuristic rules
        """
        query_lower = query.lower()
        sub_queries: list[SubQuery] = []
        
        # Get primary domain
        primary_domain = classification.domain_names[0] if classification.domain_names else "web_search"
        
        # NBA/Basketball betting pattern detection
        nba_betting_indicators = [
            "scommess", "betting", "pronostic", "odds", "quota", "value bet",
            "spread", "over/under", "moneyline", "punti", "analisi", "sistema"
        ]
        nba_game_indicators = [
            "partit", "game", "nba", "basket", "lakers", "celtics", "warriors",
            "bulls", "heat", "knicks", "stasera", "tonight", "oggi", "today"
        ]
        
        is_nba_betting = (
            any(ind in query_lower for ind in nba_betting_indicators) and
            any(ind in query_lower for ind in nba_game_indicators)
        )
        
        if is_nba_betting and primary_domain == "sports_nba":
            # Decompose NBA betting queries into game data + context data
            sub_queries = [
                SubQuery(
                    text="recupera partite NBA in programma con quote e statistiche squadre",
                    domain="sports_nba",
                    intent="nba_games_data",
                ),
                SubQuery(
                    text="recupera infortuni e classifiche NBA per le squadre in campo",
                    domain="sports_nba",
                    intent="nba_context_data",
                ),
            ]
            logger.info(
                "heuristic_decomposition_nba_betting",
                query_preview=query[:50],
                sub_query_count=len(sub_queries),
            )
            return sub_queries
        
        # Multi-intent detection via conjunctions
        conjunctions = [" e ", " poi ", " inoltre ", " and ", " then ", " also "]
        has_conjunction = any(c in query_lower for c in conjunctions)
        
        if has_conjunction and len(query.split()) > 8:
            # Split by conjunction for multi-intent queries
            parts = query
            for conj in conjunctions:
                parts = parts.replace(conj, "|||")
            
            sub_parts = [p.strip() for p in parts.split("|||") if p.strip()]
            
            if len(sub_parts) >= 2:
                for part in sub_parts:
                    # Determine domain for each part
                    part_domain = primary_domain
                    sub_queries.append(SubQuery(
                        text=part,
                        domain=part_domain,
                        intent="heuristic_split",
                    ))
                
                logger.info(
                    "heuristic_decomposition_split",
                    query_preview=query[:50],
                    sub_query_count=len(sub_queries),
                )
                return sub_queries
        
        # Analytical/deep exploration pattern
        depth_indicators = [
            "analiz", "report", "riassun", "sintetiz", "incrocia", 
            "cross", "approfond", "investiga", "raccoglie", "recupera tutt",
            "cerca tutt", "summarize", "gather", "collect", "compile"
        ]
        
        if any(ind in query_lower for ind in depth_indicators):
            # Create gather + analyze subqueries
            sub_queries = [
                SubQuery(
                    text=f"cerca e raccogli informazioni: {query}",
                    domain=primary_domain,
                    intent="heuristic_gather",
                ),
            ]
            logger.info(
                "heuristic_decomposition_analytical",
                query_preview=query[:50],
                sub_query_count=len(sub_queries),
            )
            return sub_queries
        
        # Default: return original query as single subquery (simple case)
        return [
            SubQuery(
                text=query,
                domain=primary_domain,
                intent="heuristic_single",
            )
        ]

    def _parse_decomposition(
        self,
        llm_output: str,
        classification: DomainClassification,
    ) -> list[SubQuery]:
        """Parse LLM JSON output into SubQuery objects.

        Args:
            llm_output: Raw LLM response (expected JSON array)
            classification: Original classification for fallback domains

        Returns:
            List of validated SubQuery objects
        """
        parsed = robust_json_parse(llm_output, expect_array=True)

        if not parsed or not isinstance(parsed, list):
            raise ValueError(
                f"Could not parse valid JSON array from LLM output: {llm_output[:100]}"
            )

        sub_queries = []
        valid_domains = set(self._available_domains)

        for item in parsed:
            if not isinstance(item, dict):
                continue

            # ✅ SOTA 2026: Normalize keys (removes literal quotes like "\"sub_query\"")
            item = self._normalize_dict_keys(item)

            # 🔴 CRITICAL: Defensive parsing with ALL possible key variants
            text = ""
            # Try all known variants in order of preference
            for key_variant in ["sub_query", "text", "query", "content", "message"]:
                if key_variant in item:
                    val = item[key_variant]
                    if val and isinstance(val, str):
                        text = val.strip()
                        if text:
                            break

            # If still empty, try to find ANY key containing "query" or "text"
            if not text:
                for key in item:
                    if any(kw in key.lower() for kw in ["query", "text", "content", "message"]):
                        val = item[key]
                        if val and isinstance(val, str):
                            text = val.strip()
                            if text:
                                break

            # Normalize domain and intent
            domain = item.get("domain", "").strip() if isinstance(item.get("domain"), str) else ""
            intent = item.get("intent", "").strip() if isinstance(item.get("intent"), str) else ""

            if not text:
                logger.warning("decomposition_item_missing_text", item_keys=list(item.keys()))
                continue

            # Validate domain
            if domain not in valid_domains:
                logger.warning(
                    "invalid_domain_in_decomposition",
                    domain=domain,
                    using_fallback=classification.domain_names[0]
                    if classification.domain_names
                    else "web_search",
                )
                domain = (
                    classification.domain_names[0] if classification.domain_names else "web_search"
                )

            # Create SubQuery with guaranteed valid fields
            try:
                sq = SubQuery(
                    text=text,
                    domain=domain,
                    intent=intent,
                )
                sub_queries.append(sq)
            except Exception as e:
                logger.error("failed_to_create_subquery", error=str(e), item=item)
                continue

        # ✅ SOTA 2026: Block non-actionable intents (analysis, synthesis, etc.)
        # These are handled by the system's final synthesis step.
        BLOCKED_INTENTS = {
            "analysis",
            "cross_reference",
            "summary",
            "report_generation",
            "synthesis",
        }
        initial_count = len(sub_queries)
        sub_queries = [sq for sq in sub_queries if sq.intent not in BLOCKED_INTENTS]

        if len(sub_queries) < initial_count:
            logger.info(
                "non_actionable_subqueries_filtered",
                removed=initial_count - len(sub_queries),
                remaining=len(sub_queries),
                filtered_intents=[sq.intent for sq in sub_queries if sq.intent in BLOCKED_INTENTS],
            )

        if not sub_queries:
            raise ValueError("No valid sub-queries parsed from LLM output")

        return sub_queries

    def _normalize_dict_keys(self, item: dict) -> dict:
        """Normalize dictionary keys by removing literal quotes and backslashes.

        This fixes the issue where an LLM generates JSON with literal quotes
        inside keys (e.g., {"\"sub_query\"": "..."}).

        Handles multiple levels of escaping and mixed quote types.
        """
        normalized = {}
        for key, value in item.items():
            # Iteratively remove quotes and backslashes until stable
            clean_key = str(key)
            prev_key = None
            while prev_key != clean_key:
                prev_key = clean_key
                # Remove all types of quotes and backslashes from both ends
                clean_key = clean_key.strip('"').strip("'").strip("\\").strip()

            # Also normalize the value if it's a string with quotes
            clean_value = value
            if isinstance(value, str):
                # Remove outer quotes if present
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    clean_value = value[1:-1]

            normalized[clean_key] = clean_value
        return normalized

    def should_decompose(self, query: str, classification: DomainClassification) -> bool:
        """Check if query should be decomposed.

        Uses a combination of signals to decide dynamically:
        - Multi-domain classification
        - Query length (proxy for complexity)
        - Sequential/analytical intent keywords
        - Multiple data source references

        Args:
            query: User query
            classification: Domain classification result

        Returns:
            True if decomposition recommended
        """
        # Multi-domain always benefits from decomposition
        if classification.is_multi_domain:
            return True

        # Lower word count threshold: 10 words is enough to potentially have multi-intent
        word_count = len(query.split())
        if word_count > 10:
            return True

        query_lower = query.lower()

        # Analytical/deep-exploration indicators (language-agnostic)
        depth_indicators = [
            "analiz",  # analizza, analisi, analyze, analysis
            "report",  # report, reportistica
            "riassun",  # riassunto, riassumi
            "sintetiz",  # sintetizza, sintetizzare
            "incrocia",  # incrociare, cross-reference
            "cross",  # cross-reference, cross-analysis
            "approfond",  # approfondisci, approfondimento
            "investiga",  # investiga, investigate
            "raccoglie",  # raccogliere
            "recupera tutt",  # recupera tutto/tutti
            "cerca tutt",  # cerca tutto/tutti
            "summarize",
            "gather",
            "collect",
            "compile",
        ]
        if any(indicator in query_lower for indicator in depth_indicators):
            return True

        # Sequential intent indicators
        sequential_indicators = [
            "poi",
            "dopodiché",
            "quindi",
            "e inoltre",
            "then",
            "after that",
            "also",
            "and then",
            "infine",
            "prima",
            "successivamente",
        ]
        if any(indicator in query_lower for indicator in sequential_indicators):
            return True

        # Multiple explicit data sources mentioned
        source_indicators = [
            "email",
            "mail",
            "gmail",
            "calendario",
            "calendar",
            "eventi",
            "drive",
            "documenti",
            "file",
            "cartell",
            "meet",
            "riunion",
            "call",
        ]
        sources_mentioned = sum(1 for s in source_indicators if s in query_lower)
        if sources_mentioned >= 2:
            return True

        return False
