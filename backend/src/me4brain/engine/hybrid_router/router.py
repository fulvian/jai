"""Hybrid Tool Router - Main Orchestrator.

Four-stage routing for scalable tool selection:
- Stage 0: Intent analysis + Context rewriting (NEW)
- Stage 1: Domain classification (which domains?)
- Stage 1b: Query decomposition for multi-intent (optional)
- Stage 2: Embedding retrieval (which tools?)
- Stage 3: Execution LLM with selected tools

This replaces direct tool loading with intelligent selection.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

from me4brain.engine.context_rewriter import ContextAwareRewriter, get_context_rewriter
from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
from me4brain.engine.hybrid_router.query_decomposer import QueryDecomposer
from me4brain.engine.hybrid_router.tool_retriever import (
    ToolEmbeddingManager,
    ToolRetriever,
)
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainComplexity,
    HybridRouterConfig,
    RetrievedTool,
    SubQuery,
)
from me4brain.engine.intent_analyzer import IntentAnalyzer, get_intent_analyzer
from me4brain.engine.types import ToolTask
from me4brain.llm.nanogpt import NanoGPTClient

if TYPE_CHECKING:
    from me4brain.engine.hybrid_router.llama_tool_retriever import (
        LlamaIndexToolRetriever,
    )
    from me4brain.engine.hybrid_router.tool_index import ToolIndexManager

logger = structlog.get_logger(__name__)

# Placeholder domains - these have no real tool implementations
# Queries that ONLY match these domains should be redirected to web_search
# or blocked entirely since they have no functional tools
PLACEHOLDER_DOMAINS: frozenset[str] = frozenset({"shopping", "productivity"})


class HybridToolRouter:
    """Orchestrates the multi-stage hybrid routing process.

    Flow:
    0. Intent Analysis + Context Rewriting (NEW - Stage 0)
    1. Classify query into domains (Stage 1)
    1b. Decompose multi-intent queries (optional, Stage 1b)
    2. Retrieve relevant tools via embeddings (Stage 2)
    3. Call execution LLM with selected tools only (Stage 3)

    This solves the 40KB NanoGPT payload limit by selecting only relevant tools.
    Supports both in-memory (ToolRetriever) and Qdrant-backed (LlamaIndexToolRetriever).
    """

    def __init__(
        self,
        llm_client: NanoGPTClient,
        config: HybridRouterConfig | None = None,
        tool_index: ToolIndexManager | None = None,
    ) -> None:
        self._llm = llm_client
        self._config = config or HybridRouterConfig()
        self._tool_index = tool_index  # For LlamaIndex retriever

        # These are initialized via initialize()
        self._classifier: DomainClassifier | None = None
        self._decomposer: QueryDecomposer | None = None
        self._retriever: ToolRetriever | LlamaIndexToolRetriever | None = None
        self._embedding_manager: ToolEmbeddingManager | None = None
        self._available_domains: list[str] = []
        self._initialized = False
        self._use_llamaindex = False

        # NEW: Intent Analyzer and Context Rewriter (Stage 0)
        self._intent_analyzer: IntentAnalyzer | None = None
        self._context_rewriter: ContextAwareRewriter | None = None
        self._enable_stage0_intent = True
        self._enable_context_rewrite = True

    async def initialize(
        self,
        tool_schemas: list[dict[str, Any]],
        tool_domains: dict[str, str],
        embed_fn: Callable[[str], Awaitable[list[float]]],
        llm_client: Any | None = None,
    ) -> None:
        """Initialize the router with tool data.

        Args:
            tool_schemas: List of OpenAI-compatible tool schemas
            tool_domains: Dict mapping tool_name -> domain_name
            embed_fn: Async function to embed text
            llm_client: Optional LLM client for intent analyzer and context rewriter
        """
        logger.info(
            "hybrid_router_initializing",
            tool_count=len(tool_schemas),
            domain_count=len(set(tool_domains.values())),
            use_llamaindex=self._config.use_llamaindex_retriever,
            use_decomposition=self._config.use_query_decomposition,
        )

        # Get unique domains from tools
        self._available_domains = list(set(tool_domains.values()))

        # Add skill-only domains that don't have Python tools but have skills in Qdrant
        # These domains are discovered from skills during reindexing
        # NOTE: Previously hardcoded as ["shopping"], now dynamically discovered
        # The router will auto-discover skill domains during indexing
        logger.info(
            "available_domains_loaded",
            domain_count=len(self._available_domains),
        )

        # Initialize classifier
        self._classifier = DomainClassifier(
            llm_client=self._llm,
            available_domains=self._available_domains,
            config=self._config,
        )

        # Initialize query decomposer if enabled
        if self._config.use_query_decomposition:
            self._decomposer = QueryDecomposer(
                llm_client=self._llm,
                available_domains=self._available_domains,
                config=self._config,
            )
            logger.info("query_decomposer_initialized")

        # Build tool_name -> schema map for LlamaIndex retriever
        tool_schemas_map = {}
        for schema in tool_schemas:
            if "function" in schema and "name" in schema["function"]:
                tool_schemas_map[schema["function"]["name"]] = schema

        # Choose retriever based on config
        if self._config.use_llamaindex_retriever and self._tool_index is not None:
            # Use Qdrant-backed LlamaIndex retriever
            from me4brain.engine.hybrid_router.llama_tool_retriever import (
                LlamaIndexToolRetriever,
            )

            self._retriever = LlamaIndexToolRetriever(
                tool_index=self._tool_index,
                config=self._config,
                tool_schemas_map=tool_schemas_map,  # Pass schema map for enrichment
            )
            await self._retriever.initialize()
            self._use_llamaindex = True
            logger.info(
                "retriever_initialized",
                type="LlamaIndexToolRetriever",
                schemas_loaded=len(tool_schemas_map),
            )
        else:
            # Fallback to in-memory retriever
            self._embedding_manager = ToolEmbeddingManager(embed_fn)
            await self._embedding_manager.compute_embeddings(tool_schemas)
            self._embedding_manager.set_domains(tool_domains)

            self._retriever = ToolRetriever(
                tool_schemas=self._embedding_manager.get_schemas(),
                tool_embeddings=self._embedding_manager.get_embeddings(),
                tool_domains=self._embedding_manager.get_domains(),
                embed_fn=embed_fn,
                config=self._config,
            )
            self._use_llamaindex = False
            logger.info("retriever_initialized", type="ToolRetriever")

        self._initialized = True

        # Sync runtime feature flags from global LLM config if available
        try:
            from me4brain.llm.config import get_llm_config

            llm_config = get_llm_config()
            self._enable_stage0_intent = llm_config.use_stage0_intent_analyzer
            self._enable_context_rewrite = llm_config.use_context_rewrite_for_routing
            self._config.use_query_decomposition = llm_config.use_query_decomposition
        except Exception:
            # Keep router defaults if config is unavailable
            pass

        logger.info(
            "hybrid_router_initialized",
            domains=self._available_domains,
            retriever_type="llamaindex" if self._use_llamaindex else "in_memory",
        )

        # NEW: Initialize Intent Analyzer and Context Rewriter (Stage 0)

        # Use provided llm_client or get default if not provided
        if llm_client is None:
            from me4brain.llm.nanogpt import get_llm_client

            llm_client = get_llm_client()

        self._intent_analyzer = get_intent_analyzer(llm_client)
        self._context_rewriter = get_context_rewriter(llm_client)
        logger.info("intent_analyzer_and_context_rewriter_initialized")

    async def route(
        self,
        query: str,
        context: str | None = None,
        max_tools: int = 100,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> list[ToolTask]:
        """Route a query through the hybrid pipeline.

        Args:
            query: User query
            context: Optional context information
            max_tools: Maximum tools to select for execution
            conversation_history: Recent conversation turns for context-aware rewriting
        Returns:
            List of ToolTask objects for execution
        """
        if not self._initialized:
            raise RuntimeError("HybridToolRouter not initialized. Call initialize() first.")
        if self._classifier is None or self._retriever is None:
            raise RuntimeError("HybridToolRouter components not initialized")

        # ==========================================
        # STAGE 0: Intent Analysis + Context Rewriting (NEW)
        # ==========================================
        stage0_start = time.time()

        # Step 0a: Rewrite query with conversation context if needed
        rewritten_query = query
        rewrite_result = None
        if self._enable_context_rewrite and conversation_history and self._context_rewriter:
            rewrite_result = await self._context_rewriter.rewrite(
                query=query,
                conversation_history=conversation_history,
            )
            if rewrite_result.was_rewritten:
                rewritten_query = rewrite_result.rewritten_query
                logger.info(
                    "hybrid_route_stage0a_query_rewritten",
                    original=query[:60],
                    rewritten=rewritten_query[:60],
                )

        # Step 0b: Analyze intent semantically
        intent_analysis = None
        if self._enable_stage0_intent and self._intent_analyzer:
            intent_analysis = await self._intent_analyzer.analyze(
                query=rewritten_query,
                conversation_history=conversation_history,
            )
            if intent_analysis is not None:
                logger.info(
                    "hybrid_route_stage0b_intent_analyzed",
                    intent_type=intent_analysis.intent_type.value,
                    needs_real_time=intent_analysis.data_requirements.needs_real_time_data,
                    needs_external=intent_analysis.data_requirements.needs_external_api,
                    confidence=intent_analysis.confidence,
                    suggested_domains=intent_analysis.suggested_domains,
                )

                # Early exit for pure conversation
                if (
                    intent_analysis.intent_type.value == "conversation"
                    and intent_analysis.confidence > 0.8
                ):
                    logger.info(
                        "hybrid_route_early_exit_conversation",
                        reason="Intent is pure conversation, no tools needed",
                    )
                    return []  # No tools for conversation

        stage0_time = time.time() - stage0_start

        # ==========================================
        # STAGE 1: Domain classification
        # ==========================================
        start_time = time.time()

        # Pass intent hints to classifier for better domain selection
        intent_hints = None
        if intent_analysis:
            intent_hints = {
                "suggested_domains": intent_analysis.suggested_domains,
                "intent_type": intent_analysis.intent_type.value,
                "needs_real_time": intent_analysis.data_requirements.needs_real_time_data,
            }

        classification, used_fallback = await self._classifier.classify_with_fallback(
            query=rewritten_query,
            conversation_context=conversation_history,
            intent_analysis=intent_hints,
        )
        stage1_time = time.time() - start_time

        logger.info(
            "hybrid_route_stage1_complete",
            original_query=query[:50],
            rewritten_query=rewritten_query[:50] if query != rewritten_query else None,
            domains=classification.domain_names,
            confidence=classification.confidence,
            used_fallback=used_fallback,
            is_multi_domain=classification.is_multi_domain,
            stage0_duration_ms=int(stage0_time * 1000),
            stage1_duration_ms=int(stage1_time * 1000),
        )

        # Wave 0.4: Disable placeholder domains (shopping/productivity)
        # These domains have no real tools - redirect to web_search instead
        detected_domain_names = classification.domain_names
        if detected_domain_names and all(d in PLACEHOLDER_DOMAINS for d in detected_domain_names):
            logger.info(
                "placeholder_domains_redirected_to_websearch",
                detected_domains=detected_domain_names,
                query_preview=query[:50],
            )
            # Redirect to web_search since placeholder domains have no actual tools
            # This modifies the classification in-place to use web_search
            classification = DomainClassification(
                domains=[DomainComplexity(name="web_search", complexity="medium")],
                confidence=classification.confidence,
                query_summary="Shopping/productivity queries redirected to web_search",
            )

        # Stage 1b: Query decomposition for multi-intent
        query_for_routing = rewritten_query
        sub_queries: list[SubQuery] = []
        query_is_complex = (
            classification.is_multi_domain
            or len(query_for_routing) > 100  # Lowered from 150 for better decomposition
            or self._has_multiple_intents(query_for_routing)  # Detect multiple action verbs
            or self._has_multi_intent_markers(query_for_routing)  # Detect coordination markers
        )
        if (
            self._config.use_query_decomposition
            and self._decomposer is not None
            and query_is_complex
        ):
            start_time = time.time()
            sub_queries = await self._decomposer.decompose(query_for_routing, classification)
            if not isinstance(sub_queries, list):
                sub_queries = []
            stage1b_time = time.time() - start_time
            logger.info(
                "hybrid_route_stage1b_complete",
                sub_query_count=len(sub_queries),
                sub_queries=[sq.text for sq in sub_queries],
                duration_ms=int(stage1b_time * 1000),
            )
        else:
            stage1b_time = 0

        # Stage 2: Tool retrieval
        start_time = time.time()
        if classification.needs_fallback and not classification.domains:
            # No domains at all - use global top-K
            retrieval = await self._retriever.retrieve_global_topk(query_for_routing, k=25)
        elif (
            isinstance(sub_queries, list)
            and len(sub_queries) > 0
            and self._use_llamaindex
            and callable(getattr(self._retriever, "retrieve_multi_intent", None))
        ):
            multi_intent_retriever = self._retriever
            if multi_intent_retriever is None:
                raise RuntimeError("Retriever not initialized")
            # Multi-intent retrieval with RRF fusion (LlamaIndex only)
            retrieval = await multi_intent_retriever.retrieve_multi_intent(  # type: ignore[attr-defined]
                sub_queries=sub_queries,
                classification=classification,
                original_query=query_for_routing,
            )
            logger.info(
                "hybrid_route_stage2_multi_intent",
                sub_queries_processed=len(sub_queries),
                tools_retrieved=retrieval.tool_count,
            )
        else:
            # Standard single-intent retrieval
            retrieval = await self._retriever.retrieve(query_for_routing, classification)

        logger.info(
            "hybrid_route_stage2_complete",
            tools_retrieved=retrieval.tool_count,
            payload_bytes=retrieval.total_payload_bytes,
            domains=retrieval.domains_searched,
            duration_ms=int((time.time() - start_time) * 1000),
        )

        if not retrieval.tools:
            logger.warning("no_tools_retrieved", query_preview=query_for_routing[:50])
            return []

        # Stage 3: Call execution LLM with selected tools
        start_time = time.time()
        execution_model = self._select_execution_model(
            tools_count=retrieval.tool_count,
            domains_count=len(retrieval.domains_searched),
        )

        tool_tasks = await self._execute_tool_selection(
            query=query_for_routing,
            context=context,
            tools=retrieval.tools,
            model=execution_model,
            max_tools=max_tools,
            sub_queries=sub_queries,  # Pass sub-queries for multi-intent awareness
        )

        logger.info(
            "hybrid_route_complete",
            tools_selected=[t.tool_name for t in tool_tasks],
            execution_model=execution_model,
            used_multi_intent=len(sub_queries) > 0,
            duration_ms=int((time.time() - start_time) * 1000),
        )

        return tool_tasks

    def _select_execution_model(
        self,
        tools_count: int,
        domains_count: int,
    ) -> str:
        """Select appropriate model for execution based on complexity."""
        if (
            tools_count > self._config.complex_threshold_tools
            or domains_count > self._config.complex_threshold_domains
        ):
            return self._config.execution_model_complex
        return self._config.execution_model_default

    def _has_multiple_intents(self, query: str) -> bool:
        """Detect if query contains multiple action verbs indicating multi-intent.

        Used to trigger query decomposition for complex single-domain queries.
        """
        import re

        # Expanded action verbs in Italian and English that indicate separate intents
        action_patterns = [
            # Italian verbs
            r"\bcerca\b",
            r"\btrov[ai]\b",
            r"\banalizza\b",
            r"\belabora\b",
            r"\bgenera\b",
            r"\bcrea\b",
            r"\binvia\b",
            r"\bprenota\b",
            r"\baggiorna\b",
            r"\bcontrolla\b",
            r"\bverifica\b",
            r"\bscarica\b",
            r"\bcalcola\b",
            r"\bconfr?onta\b",
            # English verbs
            r"\bsearch\b",
            r"\bfind\b",
            r"\banalyze\b",
            r"\bgenerate\b",
            r"\breport\b",
            r"\blist\b",
            r"\bget\b",
            r"\bsend\b",
            r"\bbook\b",
            r"\bupdate\b",
            r"\bcheck\b",
            r"\bverify\b",
            r"\bdownload\b",
            r"\bcalculate\b",
            r"\bcompare\b",
            r"\bexport\b",
            r"\bimport\b",
            r"\bextract\b",
            r"\bsummarize\b",
            r"\bfilter\b",
        ]

        # Count occurrences
        matches = sum(1 for p in action_patterns if re.search(p, query.lower()))

        # If 2+ action verbs found, likely multi-intent (lowered from 3)
        return matches >= 2

    def _has_multi_intent_markers(self, query: str) -> bool:
        """Detect coordination markers that indicate multiple intents.

        E.g., 'search emails AND find documents', 'first do X, then do Y'
        """
        markers = [
            " and then ",
            " and also ",
            " then ",
            " also ",
            " plus ",
            " after that ",
            " e poi ",
            " poi ",
            " quindi ",
            " inoltre ",
            " e anche ",
            ", poi ",
            "; ",  # Semicolon often separates intents
        ]

        query_lower = query.lower()
        return any(marker in query_lower for marker in markers)

    def _validate_tool_args(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        schema: dict[str, Any],
    ) -> tuple[bool, str]:
        """Validate tool arguments against schema with strict mode.

        Args:
            tool_name: Name of the tool for error messages
            arguments: Parsed arguments from LLM
            schema: JSON Schema from tool definition

        Returns:
            Tuple of (is_valid, error_message)
        """
        params = schema.get("function", {}).get("parameters", {})

        # 1. Check for additionalProperties: false
        if params.get("additionalProperties") is False:
            allowed = set(params.get("properties", {}).keys())
            incoming = set(arguments.keys())
            extra = incoming - allowed
            if extra:
                error_msg = f"Unknown parameters for {tool_name}: {extra}"
                logger.warning("invalid_tool_args_extra_params", tool=tool_name, extra=list(extra))
                return False, error_msg

        # 2. Type validation for provided arguments
        properties = params.get("properties", {})
        for key, value in arguments.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type:
                    # Basic type checking
                    type_map = {
                        "string": str,
                        "number": (int, float),
                        "integer": int,
                        "boolean": bool,
                        "array": list,
                        "object": dict,
                    }
                    expected_python_type = type_map.get(expected_type)
                    if expected_python_type and not isinstance(value, expected_python_type):
                        # Allow int for number since JSON numbers are flexible
                        if expected_type == "number" and isinstance(value, int):
                            continue
                        error_msg = f"Invalid type for {tool_name}.{key}: expected {expected_type}, got {type(value).__name__}"
                        logger.warning(
                            "invalid_tool_arg_type",
                            tool=tool_name,
                            param=key,
                            expected=expected_type,
                            actual=type(value).__name__,
                        )
                        return False, error_msg

        # 3. Required parameters check
        required = params.get("required", [])
        for req_param in required:
            if req_param not in arguments:
                error_msg = f"Missing required parameter for {tool_name}: {req_param}"
                logger.warning("missing_required_param", tool=tool_name, param=req_param)
                return False, error_msg

        return True, ""

    async def _execute_tool_selection(
        self,
        query: str,
        context: str | None,
        tools: list[RetrievedTool],
        model: str,
        max_tools: int,
        sub_queries: list[SubQuery] | None = None,
    ) -> list[ToolTask]:
        """Execute tool selection using the LLM with retrieved tools only."""
        from me4brain.llm.models import (
            LLMRequest,
            Message,
            MessageRole,
            Tool,
            ToolFunction,
        )

        # Build system prompt
        current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_prompt = self._build_execution_prompt(max_tools, current_dt, sub_queries)

        # Build user message
        user_content = query
        if context:
            user_content = f"Context: {context}\n\nQuery: {query}"

        # Convert tool schemas to Tool model format
        tool_models = []
        for t in tools:
            schema = t.schema
            func = schema.get("function", {})
            tool_models.append(
                Tool(
                    type="function",
                    function=ToolFunction(
                        name=func.get("name", ""),
                        description=func.get("description", ""),
                        parameters=func.get("parameters", {}),
                    ),
                )
            )

        try:
            # DEBUG: Log exact prompt being sent
            logger.info(
                "llm_selection_request",
                model=model,
                tools_count=len(tool_models),
                has_context=context is not None,
                query_preview=query[:100],
            )

            request = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=system_prompt),
                    Message(role=MessageRole.USER, content=user_content),
                ],
                model=model,
                tools=tool_models if tool_models else None,
                tool_choice="auto" if tool_models else "none",
                temperature=0.1,
            )

            response = await self._llm.generate_response(request)

            # Parse tool calls
            message = response.choices[0].message
            tool_calls = message.tool_calls or []

            # FIX B1: Retry with explicit instruction if no tool calls (shouldn't happen with required)
            if not tool_calls and tool_models:
                logger.warning(
                    "tool_selection_no_calls_retry",
                    model=model,
                    tools_offered=len(tool_models),
                )
                # Add explicit instruction to force tool usage
                retry_prompt = (
                    system_prompt
                    + "\n\n**CRITICAL**: You MUST call at least one tool. Do NOT respond without a tool call."
                )
                retry_request = LLMRequest(
                    messages=[
                        Message(role=MessageRole.SYSTEM, content=retry_prompt),
                        Message(role=MessageRole.USER, content=user_content),
                    ],
                    model=model,
                    tools=tool_models,
                    tool_choice="required",
                    temperature=0.0,  # Lower temperature for retry
                )
                response = await self._llm.generate_response(retry_request)
                message = response.choices[0].message
                tool_calls = message.tool_calls or []

            # Build schema lookup for validation
            schema_lookup: dict[str, dict[str, Any]] = {t.tool_name: t.schema for t in tools}

            tasks = []
            for tc in tool_calls[:max_tools]:
                try:
                    # Robust parsing: LLM might return malformed or duplicated JSON
                    raw_args = tc.function.arguments

                    # First attempt: direct parse
                    try:
                        arguments = json.loads(raw_args)
                    except json.JSONDecodeError:
                        # Second attempt: find FIRST valid JSON object
                        # LLM sometimes duplicates entire JSON inline
                        first_brace = raw_args.find("{")
                        if first_brace != -1:
                            # Try progressive substrings to find valid JSON
                            arguments = {}
                            depth = 0
                            start = first_brace
                            for i, char in enumerate(raw_args[first_brace:], first_brace):
                                if char == "{":
                                    depth += 1
                                elif char == "}":
                                    depth -= 1
                                    if depth == 0:
                                        # Found complete object
                                        try:
                                            arguments = json.loads(raw_args[start : i + 1])
                                            break  # Use first valid object
                                        except json.JSONDecodeError:
                                            # Object malformed, try regex extraction
                                            break

                            # If still empty, try regex for key fields
                            if not arguments:
                                import re

                                # Extract common patterns
                                patterns = [
                                    (r'"agent_type"\s*:\s*"([^"]+)"', "agent_type"),
                                    (r'"name"\s*:\s*"([^"]+)"', "name"),
                                    (r'"ticker"\s*:\s*"([^"]+)"', "ticker"),
                                    (r'"goal"\s*:\s*"([^"]+)"', "goal"),
                                    (r'"symbol"\s*:\s*"([^"]+)"', "symbol"),
                                    (r'"query"\s*:\s*"([^"]+)"', "query"),
                                ]
                                for pattern, key in patterns:
                                    match = re.search(pattern, raw_args)
                                    if match:
                                        arguments[key] = match.group(1)
                        else:
                            arguments = {}
                except Exception:
                    arguments = {}

                # ✅ SOTA 2026: Normalize argument keys (remove literal quotes)
                if arguments and isinstance(arguments, dict):
                    arguments = {
                        k.strip('"').strip("'").strip("\\"): v for k, v in arguments.items()
                    }

                # ✅ Wave 1.3: Strict schema validation
                tool_name = tc.function.name
                schema = schema_lookup.get(tool_name)
                if schema is not None:
                    is_valid, error_msg = self._validate_tool_args(
                        tool_name=tool_name,
                        arguments=arguments,
                        schema=schema,
                    )
                    if not is_valid:
                        logger.warning(
                            "tool_argument_validation_failed",
                            tool=tool_name,
                            error=error_msg,
                            arguments=arguments,
                        )
                        # Keep arguments but log warning - don't block execution
                        # This prevents silent failures while allowing execution to proceed
                else:
                    logger.debug(
                        "tool_schema_not_found_for_validation",
                        tool=tool_name,
                    )

                tasks.append(
                    ToolTask(
                        tool_name=tool_name,
                        arguments=arguments,
                        call_id=tc.id,
                    )
                )

            logger.info(
                "tool_selection_complete",
                tools_selected=len(tasks),
                tool_names=[t.tool_name for t in tasks],
                model=model,
            )

            return tasks

        except Exception as e:
            logger.error(
                "execution_tool_selection_failed",
                error=str(e),
                model=model,
                tools_count=len(tools),
            )
            return []

    def _build_execution_prompt(
        self,
        max_tools: int,
        current_datetime: str,
        sub_queries: list[SubQuery] | None = None,
    ) -> str:
        """Build system prompt for tool execution LLM."""
        # Build sub-queries section if multi-intent
        sub_queries_section = ""
        if sub_queries and len(sub_queries) > 1:
            sub_query_list = "\n".join(
                f"  {i + 1}. [{sq.domain}] {sq.text}" for i, sq in enumerate(sub_queries)
            )
            sub_queries_section = f"""

## ⚠️ MANDATORY MULTI-INTENT EXECUTION
This query has been decomposed into {len(sub_queries)} sub-queries.
**You MUST call at least one tool for EACH sub-query below** - no exceptions:

{sub_query_list}

CRITICAL REQUIREMENTS:
- You MUST address ALL {len(sub_queries)} sub-queries, not just some of them
- Each sub-query needs AT LEAST one tool call
- If a sub-query asks to "save", "create", or "write" a document, you MUST call the appropriate create tool (e.g., google_docs_create)
- Do NOT hallucinate results - only report what tools actually return
- If you cannot find an appropriate tool for a sub-query, explicitly state that"""

        return f"""You are an intelligent assistant that helps users by calling the appropriate tools.

Current date and time: {current_datetime}{sub_queries_section}

IMPORTANT RULES:
1. Select the MOST APPROPRIATE tools for the user's request.
2. ALWAYS extract mandatory parameters from the user's query.
3. For search tools (like google_gmail_search, google_drive_search, google_calendar_list), use the most relevant search terms as the 'query' parameter.
4. Use the EXACT parameter names and types as specified in tool definitions.
5. You can call multiple tools if needed (max {max_tools}). For multi-intent queries, you MUST call multiple tools.
6. If you cannot help with the request, respond in natural language without calling tools.
7. NEVER make up URLs, document IDs, or results that weren't returned by actual tool calls.
8. For SHOPPING/MARKETPLACE tools: if the tool returns an error, empty results, or a "_meta" field with type "instructions_only", explicitly tell the user you couldn't fetch real results. NEVER invent product listings, prices, or URLs.

RECURRING vs ONE-TIME QUERIES:
- If user wants a RECURRING/SCHEDULED task (e.g., "every day", "each morning", "weekly") → use create_autonomous_agent
- If user wants CONDITIONAL MONITORING (e.g., "alert me when", "notify me if") → use create_autonomous_agent
- If user wants IMMEDIATE/NOW analysis without scheduling → use analysis tools (fmp_*, yahoo_*, etc.)
- Key: "analyze X every day" → create_autonomous_agent | "analyze X now" → finance tools

EXAMPLES OF CORRECT MULTI-TOOL CALLS:
- User: "Search emails and create a summary"
  Call: google_gmail_search(...) + google_docs_create(...)

- User: "Find products and save the results"
  Call: [search tools for the products] + [create tool for saving]

PARAMETER EXTRACTION (STEP-BY-STEP):
8. For EVERY tool call, you MUST populate parameters:
   a) LIST all entities in query: nouns (names, symbols, tickers), verbs (actions), modifiers (daily, when, if), numbers
   b) MATCH entities to the tool parameter descriptions in the schema
   c) INFER implied params from context when reasonable (e.g., "daily" → schedule, "below X" → condition + threshold)
   d) REQUIRED params MUST be filled - NEVER leave them empty
   e) Output ONLY valid JSON matching schema exactly
   f) If unsure about a param value, use the most reasonable interpretation from the query

You have access to a curated set of tools specifically selected for this query.
If the query has multiple intents, call one or more tools for EACH intent."""

    async def add_tool(
        self,
        tool_name: str,
        schema: dict[str, Any],
        domain: str,
    ) -> None:
        """Add or update a tool dynamically (e.g., from skills).

        Use this when new skills are created to add them to the router.
        """
        if self._use_llamaindex and self._tool_index:
            await self._tool_index.add_tool(tool_name, schema, domain)
        elif self._embedding_manager:
            await self._embedding_manager.update_tool(tool_name, schema, domain)

        # Add domain if new
        if domain not in self._available_domains:
            self._available_domains.append(domain)
            # Recreate classifier with updated domains
            self._classifier = DomainClassifier(
                llm_client=self._llm,
                available_domains=self._available_domains,
                config=self._config,
            )

        # Update retriever with new data (only for legacy retriever)
        if not self._use_llamaindex and self._embedding_manager:
            self._retriever = ToolRetriever(
                tool_schemas=self._embedding_manager.get_schemas(),
                tool_embeddings=self._embedding_manager.get_embeddings(),
                tool_domains=self._embedding_manager.get_domains(),
                embed_fn=self._embedding_manager._embed_fn,
                config=self._config,
            )

        logger.info("tool_added_to_router", tool=tool_name, domain=domain)

    def get_stats(self) -> dict[str, Any]:
        """Get router statistics."""
        if not self._initialized:
            return {"initialized": False}

        tools_count = 0
        if self._use_llamaindex and self._tool_index:
            stats = self._tool_index.get_stats()
            tools_count = stats.get("total_tools", 0)
        elif self._embedding_manager:
            tools_count = len(self._embedding_manager.get_embeddings())

        return {
            "initialized": True,
            "domains": self._available_domains,
            "domain_count": len(self._available_domains),
            "tools_embedded": tools_count,
            "config": {
                "router_model": self._config.router_model,
                "execution_model_default": self._config.execution_model_default,
                "execution_model_complex": self._config.execution_model_complex,
                "max_payload_bytes": self._config.max_payload_bytes,
                "confidence_threshold": self._config.confidence_threshold,
            },
        }


# Singleton instance for HybridToolRouter
_router_instance: HybridToolRouter | None = None


def _reset_router_singleton() -> None:
    """Reset router singleton to pick up new configuration.

    Called when LLM config is updated via API to ensure router uses new settings.
    """
    global _router_instance
    _router_instance = None
    logger.info("hybrid_router_singleton_reset", reason="config_changed")
