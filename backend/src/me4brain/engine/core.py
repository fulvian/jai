"""Tool Calling Engine - Main orchestrator class.

This is the primary interface for the tool calling system.
Combines Router → Executor → Synthesizer into a simple API.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import structlog

from me4brain.core.skills.crystallizer import Crystallizer

# Skill auto-learning components
from me4brain.core.skills.monitor import ExecutionMonitor
from me4brain.core.skills.types import ExecutionTrace
from me4brain.engine.catalog import ToolCatalog
from me4brain.engine.executor import ParallelExecutor
from me4brain.engine.feature_flags import get_feature_flag_manager
from me4brain.engine.router import ToolRouter
from me4brain.engine.synthesizer import ResponseSynthesizer
from me4brain.engine.types import EngineResponse, ToolResult, ToolTask
from me4brain.engine.unified_intent_analyzer import IntentType, UnifiedIntentAnalyzer
from me4brain.llm.provider_factory import resolve_model_client

# Iterative execution (ReAct pattern) - imported lazily to avoid circular imports
# from me4brain.engine.iterative_executor import IterativeExecutor, ExecutionContext

logger = structlog.get_logger(__name__)


def _should_use_unified_intent(config: Any, session_key: str) -> bool:
    """Decide whether unified analyzer should run for this request."""
    if config is None:
        return False

    if getattr(config, "use_unified_intent_analyzer", False):
        return True

    ff = get_feature_flag_manager()
    return ff.should_use_unified_analyzer(session_key)


class _HybridRouterAdapter:
    """Adapter to make HybridToolRouter compatible with ToolRouter interface.

    This allows the ToolCallingEngine to use either router seamlessly.
    Also exposes components needed for iterative execution.
    """

    def __init__(
        self,
        hybrid_router,  # HybridToolRouter
        catalog: ToolCatalog,
    ) -> None:
        self._hybrid_router = hybrid_router
        self._catalog = catalog

    async def route(
        self,
        query: str,
        context: str | None = None,
        max_tools: int = 100,
    ) -> list[ToolTask]:
        """Route using hybrid two-stage process."""
        return await self._hybrid_router.route(query, context, max_tools)

    def get_stats(self) -> dict:
        """Get router statistics."""
        return self._hybrid_router.get_stats()

    # Expose components for iterative execution
    @property
    def retriever(self):
        """Get the underlying retriever for iterative execution."""
        return self._hybrid_router._retriever

    @property
    def decomposer(self):
        """Get the query decomposer for planning."""
        return self._hybrid_router._decomposer

    @property
    def classifier(self):
        """Get the domain classifier."""
        return self._hybrid_router._classifier

    @property
    def llm_client(self):
        """Get the LLM client."""
        return self._hybrid_router._llm

    def _has_multi_intent_markers(self, query: str) -> bool:
        """Proxy to the underlying router's multi-intent detection."""
        return self._hybrid_router._has_multi_intent_markers(query)


class ToolCallingEngine:
    """Main engine for LLM-based tool calling.

    Provides a clean interface for:
    1. Full pipeline: query → route → execute → synthesize
    2. Individual components for fine-grained control
    3. Direct tool execution

    Example:
        # Simple usage
        engine = await ToolCallingEngine.create()
        response = await engine.run("Prezzo Bitcoin e meteo Roma")
        print(response.answer)

        # Advanced: just routing
        tasks = await engine.route("Prezzo Bitcoin")

        # Direct tool call
        result = await engine.execute_tool("coingecko_price", {"ids": "bitcoin"})
    """

    def __init__(
        self,
        catalog: ToolCatalog,
        router: ToolRouter,
        executor: ParallelExecutor,
        synthesizer: ResponseSynthesizer,
        analyzer: UnifiedIntentAnalyzer | None = None,
        config: Any | None = None,
        iterative_executor: Any | None = None,
    ) -> None:
        """Initialize engine with components.

        Use ToolCallingEngine.create() for easy setup.

        Args:
            catalog: Tool catalog with all tools
            router: LLM-based router
            executor: Parallel executor
            synthesizer: Response synthesizer
            analyzer: Unified intent analyzer (replaces conversational bypass)
        """
        self._catalog = catalog
        self._router = router
        self._executor = executor
        self._synthesizer = synthesizer
        self._analyzer = analyzer
        self._config = config
        self._iterative_executor = iterative_executor

        # Skill auto-learning (Voyager pattern)
        self._crystallizer: Crystallizer | None = None
        self._execution_monitor: ExecutionMonitor | None = None
        self._enable_skill_learning = False

    def enable_skill_learning(self, crystallizer: Crystallizer) -> None:
        """Abilita auto-learning delle skills.

        Args:
            crystallizer: Crystallizer instance per generare skills
        """
        self._crystallizer = crystallizer
        self._execution_monitor = ExecutionMonitor(
            on_trace_complete=self._on_trace_complete,
            min_tools_for_crystallization=2,
        )
        self._enable_skill_learning = True
        logger.info("skill_learning_enabled")

    async def _on_trace_complete(self, trace: ExecutionTrace) -> None:
        """Callback quando una trace è completa - cristallizza se appropriato."""
        if not self._crystallizer:
            return

        try:
            skill = await self._crystallizer.process_trace(trace)
            if skill:
                logger.info(
                    "skill_crystallized",
                    skill_name=skill.name,
                    tool_count=len(trace.tool_chain),
                )
        except Exception as e:
            logger.warning("skill_crystallization_failed", error=str(e))

    @classmethod
    async def create(
        cls,
        routing_model: str | None = None,
        synthesis_model: str | None = None,
        timeout_seconds: float = 60.0,
        max_concurrent: int = 5,
    ) -> ToolCallingEngine:
        """Factory to create engine with HYBRID ROUTING (default since v0.14.1).

        Uses Two-Stage Semantic Routing:
        - Stage 1: Domain classification via LLM
        - Stage 2: Embedding-based tool retrieval (BGE-M3)

        This significantly reduces payload size and eliminates NanoGPT 503 errors.

        Args:
            routing_model: Model for routing (default: from config)
            synthesis_model: Model for synthesis (default: from config)
            timeout_seconds: Timeout per tool execution
            max_concurrent: Max concurrent tool executions

        Returns:
            Configured ToolCallingEngine with hybrid routing
        """
        # Delegate to hybrid routing implementation
        return await cls._create_with_hybrid_routing(
            routing_model=routing_model,
            synthesis_model=synthesis_model,
            timeout_seconds=timeout_seconds,
            max_concurrent=max_concurrent,
        )

    @classmethod
    async def _create_with_hybrid_routing(
        cls,
        routing_model: str | None = None,
        synthesis_model: str | None = None,
        timeout_seconds: float = 60.0,
        max_concurrent: int = 5,
    ) -> ToolCallingEngine:
        """Factory to create engine with HYBRID routing.

        Uses Two-Stage Hybrid Router for scalable tool selection:
        - Stage 1: Domain classification
        - Stage 2: Embedding-based tool retrieval

        This bypasses the 40KB NanoGPT payload limit by selecting
        only relevant tools dynamically.

        Args:
            routing_model: Model for routing (default: Mistral Large 3)
            synthesis_model: Model for synthesis (default: Mistral Large 3)
            timeout_seconds: Timeout per tool execution
            max_concurrent: Max concurrent tool executions

        Returns:
            Configured ToolCallingEngine with hybrid routing
        """
        from me4brain.engine.hybrid_router import HybridToolRouter
        from me4brain.engine.hybrid_router.tool_index import ToolIndexManager
        from me4brain.engine.hybrid_router.types import HybridRouterConfig
        from me4brain.llm.config import get_llm_config
        from me4brain.llm.provider_factory import get_reasoning_client

        config = get_llm_config()
        llm_client = get_reasoning_client()

        # Resolve routing and synthesis models from config
        # Respect dashboard preferences: LLM_ROUTING_MODEL and LLM_SYNTHESIS_MODEL
        if routing_model is None:
            routing_model = config.model_routing  # Use dashboard-configured routing model
        if synthesis_model is None:
            synthesis_model = config.model_synthesis  # Use dashboard-configured synthesis model

        # Create catalog and discover tools
        catalog = ToolCatalog()
        tools_count = await catalog.discover_from_domains()

        # Phase 1: Register skill handlers (Skills Integration)
        skills_registered = await cls._register_skill_handlers(catalog)
        if skills_registered > 0:
            logger.info(
                "skills_handlers_registered",
                count=skills_registered,
            )

        # Create embedding function using BGE-M3 service
        async def embed_fn(text: str) -> list[float]:
            """Embed text using BGE-M3 via the embedding service.

            Uses run_in_executor because BGEM3Service.embed_query is synchronous.
            """
            import asyncio

            from me4brain.embeddings.bge_m3 import get_embedding_service

            service = get_embedding_service()  # Sincrono, ritorna singleton
            loop = asyncio.get_event_loop()
            # Run sync method in thread pool to avoid blocking
            embedding = await loop.run_in_executor(None, service.embed_query, text)
            return embedding

        # Create ToolIndexManager for Qdrant-backed retrieval
        tool_index = None
        router_config = HybridRouterConfig()

        # 🎯 FIX: Sincronizza i modelli con la configurazione globale
        router_config.router_model = routing_model
        router_config.decomposition_model = routing_model
        router_config.execution_model_default = synthesis_model
        router_config.execution_model_complex = synthesis_model
        router_config.reranker_model = routing_model

        if router_config.use_llamaindex_retriever:
            try:
                from qdrant_client import AsyncQdrantClient, QdrantClient

                from me4brain.config import get_settings

                settings = get_settings()
                qdrant_client = QdrantClient(
                    host=settings.qdrant_host, port=settings.qdrant_http_port, timeout=60
                )
                async_qdrant_client = AsyncQdrantClient(
                    host=settings.qdrant_host, port=settings.qdrant_http_port, timeout=60
                )

                tool_index = ToolIndexManager(
                    qdrant_client=qdrant_client,
                    async_qdrant_client=async_qdrant_client,
                )
                await tool_index.initialize()

                logger.info(
                    "tool_index_manager_initialized",
                    qdrant_url=f"http://{settings.qdrant_host}:{settings.qdrant_http_port}",
                    stats=tool_index.get_stats(),
                )
            except Exception as e:
                logger.warning(
                    "tool_index_manager_creation_failed",
                    error=str(e),
                    fallback="in_memory_retriever",
                )
                tool_index = None

        # Create hybrid router with optional ToolIndexManager
        hybrid_router = HybridToolRouter(
            llm_client,
            config=router_config,
            tool_index=tool_index,
        )

        # Initialize with tool data
        schemas = catalog.get_function_schemas()
        tool_domains = catalog.get_tool_domains()

        # CRITICAL: Build tool index in Qdrant (was missing!)
        # Must be called AFTER schemas and tool_domains are extracted from catalog
        if tool_index is not None:
            try:
                indexed_count = await tool_index.build_from_catalog(
                    tool_schemas=schemas,
                    tool_domains=tool_domains,
                    force_rebuild=False,  # Use hash-based change detection
                )
                logger.info(
                    "tool_index_built",
                    indexed_count=indexed_count,
                    total_tools=len(schemas),
                )
            except Exception as e:
                logger.warning("tool_index_build_failed", error=str(e))

        await hybrid_router.initialize(
            tool_schemas=schemas,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
            llm_client=llm_client,
        )

        # Create adapter that wraps HybridToolRouter as ToolRouter interface
        router = _HybridRouterAdapter(hybrid_router, catalog)

        from me4brain.engine.iterative_executor import IterativeExecutor
        from me4brain.llm.provider_factory import get_tool_calling_client

        tc_client = get_tool_calling_client()
        tc_model = config.ollama_model if config.use_local_tool_calling else routing_model

        executor = ParallelExecutor(
            catalog,
            timeout_seconds=timeout_seconds,
            max_concurrent=20,  # Increased from 5 for concurrent stress
            max_global_concurrent=50,  # Increased from default 20
        )
        synthesizer = ResponseSynthesizer(
            llm_client,
            synthesis_model,
            is_local=config.use_local_tool_calling,
        )

        # Iterative executor initialized with tool-calling specialized provider
        iterative_executor_instance = IterativeExecutor(
            llm_client=llm_client,
            retriever=router.retriever,
            executor=executor,
            model=routing_model,  # Primary reasoning model (Mistral)
            tool_calling_llm=tc_client,  # Specialized provider (Ollama)
            tool_calling_model=tc_model,  # Specialized model (lfm2.5)
        )

        logger.info(
            "engine_created_with_hybrid_routing",
            tools_discovered=tools_count,
            domains=catalog.get_all_domains(),
            routing_model=routing_model,
            synthesis_model=synthesis_model,
            use_llamaindex=tool_index is not None,
        )

        # Initialize UnifiedIntentAnalyzer only when enabled by config/rollout
        analyzer = UnifiedIntentAnalyzer(llm_client, config)
        if _should_use_unified_intent(config, "engine_create_hybrid"):
            await analyzer.warm_up()

        return cls(
            catalog=catalog,
            router=router,
            executor=executor,
            synthesizer=synthesizer,
            analyzer=analyzer,
            config=config,
            iterative_executor=iterative_executor_instance,
        )

    async def _execute_with_monitoring(
        self, tasks: list[ToolTask], session_id: str
    ) -> list[ToolResult]:
        """Esegue tasks con monitoring per skill learning.

        Wrappa l'executor standard aggiungendo hook on_tool_start/on_tool_end
        per ogni tool eseguito.

        Args:
            tasks: Lista di ToolTask da eseguire
            session_id: ID della sessione per isolamento traccia

        Returns:
            Lista di ToolResult
        """
        if not self._execution_monitor or not self._enable_skill_learning:
            # No monitoring, usa executor diretto
            return await self._executor.execute(tasks)

        results: list[ToolResult] = []

        # Esegui con monitoring per ciascun tool
        for task in tasks:
            # Hook start
            await self._execution_monitor.on_tool_start(session_id, task.tool_name, task.arguments)

            # Esegui singolo tool
            result = await self._executor.execute_single(task)
            results.append(result)

            # Hook end
            await self._execution_monitor.on_tool_end(
                session_id=session_id,
                tool_name=task.tool_name,
                result=result.data,
                success=result.success,
                error=result.error,
            )

        return results

    async def _populate_empty_docs(
        self,
        results: list[ToolResult],
        tasks: list[ToolTask],
        synthesized_content: str,
        original_query: str = "",
    ) -> None:
        """Ensure Google Docs creation/population after synthesis.

        Handles two scenarios:
        1. A doc was created during execution but is empty → insert content
        2. No doc was created but user requested saving → create + populate

        Args:
            results: Tool execution results
            tasks: Tool tasks that were executed
            synthesized_content: Final synthesized response text
            original_query: Original user query (for intent detection)
        """
        if not synthesized_content:
            return

        doc_populated = False

        # Scenario 1: Find existing empty docs and populate them
        for task, result in zip(tasks, results, strict=False):
            if task.tool_name != "google_docs_create":
                continue

            if not result.success or not result.data:
                continue

            # Extract document ID
            doc_id = None
            if isinstance(result.data, dict):
                doc_id = result.data.get("document_id") or result.data.get("id")
                doc_url = (
                    result.data.get("url")
                    or result.data.get("link")
                    or result.data.get("document_url")
                )
                if not doc_id and doc_url:
                    import re

                    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_url)
                    if match:
                        doc_id = match.group(1)

            if not doc_id:
                continue

            # Populate the empty doc
            logger.info(
                "populating_empty_doc", doc_id=doc_id, content_length=len(synthesized_content)
            )
            try:
                insert_executor = self._catalog.get_executor("google_docs_insert_text")
                if insert_executor:
                    await insert_executor(document_id=doc_id, text=synthesized_content, index=1)
                    logger.info("empty_doc_populated", doc_id=doc_id)
                    doc_populated = True
            except Exception as e:
                logger.error("empty_doc_populate_failed", doc_id=doc_id, error=str(e))

        # Scenario 2: No doc was created, but user wanted one → create it now
        if not doc_populated and self._should_create_doc(original_query):
            await self._create_doc_post_synthesis(original_query, synthesized_content)

    def _should_create_doc(self, query: str) -> bool:
        """Detect if the user's query implies saving to Google Docs."""
        if not query:
            return False
        q = query.lower()
        # Italian + English patterns for "save/create a document"
        save_patterns = [
            "salva su google doc",
            "salva in google doc",
            "salva come documento",
            "salva come google doc",
            "crea un documento google",
            "crea un google doc",
            "crea il documento",
            "crea il report",
            "salvalo su google",
            "salvalo in un documento",
            "save to google doc",
            "create a google doc",
            "metti su google doc",
            "scrivi su google doc",
        ]
        return any(pattern in q for pattern in save_patterns)

    async def _create_doc_post_synthesis(
        self,
        query: str,
        content: str,
    ) -> None:
        """Create a Google Doc with synthesized content post-synthesis."""
        # Generate title from query
        title = self._generate_doc_title(query)

        logger.info(
            "post_synthesis_doc_create",
            title=title,
            content_length=len(content),
        )

        try:
            docs_create_executor = self._catalog.get_executor("google_docs_create")
            if docs_create_executor:
                result = await docs_create_executor(
                    title=title,
                    content=content,
                )
                if isinstance(result, dict) and result.get("document_id"):
                    logger.info(
                        "post_synthesis_doc_created",
                        doc_id=result["document_id"],
                        title=title,
                        link=result.get("link", ""),
                    )
                else:
                    logger.warning("post_synthesis_doc_create_no_id", result=str(result)[:200])
            else:
                logger.warning("google_docs_create_executor_not_found")
        except Exception as e:
            logger.error("post_synthesis_doc_create_failed", error=str(e))

    @staticmethod
    def _generate_doc_title(query: str) -> str:
        """Generate a concise document title from the user query."""
        import re
        from datetime import datetime

        # Remove common prefixes
        q = query.strip()
        for prefix in [
            "crea un report dettagliato",
            "crea un report",
            "crea un documento",
            "genera un report",
            "fammi un report",
            "scrivi un report",
        ]:
            if q.lower().startswith(prefix):
                q = q[len(prefix) :].strip()
                break

        # Clean and truncate
        q = re.sub(r"[^\w\s\-àèéìòù]", "", q, flags=re.UNICODE)
        words = q.split()[:8]  # Max 8 words
        title = " ".join(words).strip()

        if not title:
            title = "Report"

        date_str = datetime.now().strftime("%Y%m%d")
        return f"{title.title()}_{date_str}"

    async def run(
        self,
        query: str,
        context: str | None = None,
        max_tools: int = 100,
    ) -> EngineResponse:
        """Full pipeline: route → execute → synthesize.

        Args:
            query: User's natural language query
            context: Optional additional context
            max_tools: Maximum tools to call

        Returns:
            EngineResponse with answer and tool results
        """
        start_time = time.monotonic()

        # Step 0: Security - Validate input with guardrail
        from me4brain.engine.guardrail import ThreatLevel, get_guardrail

        guardrail = get_guardrail()
        input_validation = guardrail.validate_input(query)

        if input_validation.threat_level == ThreatLevel.DANGEROUS:
            logger.warning(
                "engine_input_blocked",
                query_preview=query[:50],
                reason=input_validation.reason,
                patterns=input_validation.matched_patterns,
            )
            return EngineResponse(
                answer="⚠️ La richiesta contiene pattern potenzialmente pericolosi ed è stata bloccata per sicurezza.",
                tool_results=[],
                tools_called=[],
                total_latency_ms=(time.monotonic() - start_time) * 1000,
            )

        # Sanitize input if suspicious
        sanitized_query = query
        if input_validation.threat_level == ThreatLevel.SUSPICIOUS:
            sanitized_query = guardrail.sanitize_input(query)
            logger.info(
                "engine_input_sanitized",
                original_len=len(query),
                sanitized_len=len(sanitized_query),
            )

        # Skill Learning: Start trace if enabled
        import uuid

        session_id = str(uuid.uuid4())
        if self._execution_monitor and self._enable_skill_learning:
            self._execution_monitor.start_trace(session_id, sanitized_query)

        use_unified_intent = _should_use_unified_intent(self._config, session_id)
        analysis = None
        if use_unified_intent and self._analyzer is not None:
            analysis = await self._analyzer.analyze(sanitized_query, context)

        if analysis is not None and analysis.intent == IntentType.CONVERSATIONAL:
            logger.info(
                "conversational_query_detected",
                query_preview=sanitized_query[:50],
                confidence=analysis.confidence,
            )

            # Use local tool calling client if configured, otherwise router client
            from me4brain.llm.provider_factory import get_tool_calling_client

            conv_client = (
                get_tool_calling_client()
                if self._config.use_local_tool_calling
                else self._router.llm_client
            )

            # Select model based on provider type
            from me4brain.llm.ollama import OllamaClient

            conv_model = (
                self._config.ollama_model
                if isinstance(conv_client, OllamaClient)
                else self._config.model_routing
            )

            from me4brain.llm.models import LLMRequest, Message, MessageRole

            resolved_client, actual_model = resolve_model_client(conv_model)
            request = LLMRequest(
                messages=[
                    Message(
                        role=MessageRole.SYSTEM,
                        content="Sei un assistente amichevole. Rispondi in italiano in modo conciso.",
                    ),
                    Message(role=MessageRole.USER, content=sanitized_query),
                ],
                model=actual_model,
                temperature=0.7,
            )
            response = await resolved_client.generate_response(request)
            return EngineResponse(
                answer=response.choices[0].message.content
                if response.choices
                else "Ciao! Come posso aiutarti?",
                tool_results=[],
                tools_called=[],
                total_latency_ms=(time.monotonic() - start_time) * 1000,
            )

        # Step 1: Route - LLM decides which tools to call (using domains from intent analysis)
        tasks = await self._router.route(sanitized_query, context, max_tools)

        if not tasks:
            logger.warning(
                "engine_no_tools_selected",
                query_preview=query[:100],
                context_provided=context is not None,
                router_type=type(self._router).__name__,
                domains=analysis.domains if analysis is not None else [],
            )
            return EngineResponse(
                answer="Non ho trovato strumenti specifici per questa richiesta. Posso aiutarti in altro modo?",
                tool_results=[],
                tools_called=[],
                total_latency_ms=(time.monotonic() - start_time) * 1000,
            )

        logger.info(
            "engine_tools_selected",
            count=len(tasks),
            tools=[t.tool_name for t in tasks],
            domains=analysis.domains if analysis is not None else [],
        )

        # Step 2: Execute - Run all tools in parallel (with monitoring)
        results = await self._execute_with_monitoring(tasks, session_id=session_id)

        # Step 3: Synthesize - Combine results into response
        answer = await self._synthesizer.synthesize(query, results, context)

        # Step 3.5: Post-synthesis - Populate empty Google Docs with synthesized content
        await self._populate_empty_docs(results, tasks, answer, original_query=query)

        # Skill Learning: Finalize trace and trigger crystallization
        if self._execution_monitor and self._enable_skill_learning:
            # Determina se l'esecuzione è stata un successo
            success = any(r.success for r in results)
            trace = self._execution_monitor.finalize_trace(
                session_id=session_id,
                final_output=answer,
                overall_success=success,
            )
            # Callback asincrono per crystallization
            if trace and success:
                import asyncio

                asyncio.create_task(self._on_trace_complete(trace))

        # Step 4: Security - Validate output
        output_validation = guardrail.validate_output(answer)
        if output_validation.threat_level == ThreatLevel.DANGEROUS:
            logger.warning(
                "engine_output_filtered",
                reason=output_validation.reason,
            )
            answer = guardrail.filter_output(answer)

        total_latency = (time.monotonic() - start_time) * 1000

        logger.info(
            "engine_run_complete",
            query_preview=query[:50],
            tools_called=len(tasks),
            successful=sum(1 for r in results if r.success),
            total_latency_ms=round(total_latency, 2),
        )

        return EngineResponse(
            answer=answer,
            tool_results=results,
            tools_called=[t.tool_name for t in tasks],
            reasoning_trace=[t.reasoning for t in tasks if t.reasoning],
            total_latency_ms=total_latency,
        )

    async def run_streaming(
        self,
        query: str,
        context: str | None = None,
        max_tools: int = 100,
    ) -> AsyncIterator[str]:
        """Full pipeline with streaming response.

        Yields answer chunks as they're generated.

        Args:
            query: User's natural language query
            context: Optional context
            max_tools: Maximum tools to call

        Yields:
            Response chunks
        """
        # Step 0: Security - Validate input with guardrail
        from me4brain.engine.guardrail import ThreatLevel, get_guardrail

        guardrail = get_guardrail()
        input_validation = guardrail.validate_input(query)

        if input_validation.threat_level == ThreatLevel.DANGEROUS:
            logger.warning(
                "engine_streaming_input_blocked",
                query_preview=query[:50],
                reason=input_validation.reason,
            )
            yield "⚠️ La richiesta contiene pattern potenzialmente pericolosi ed è stata bloccata per sicurezza."
            return

        # Sanitize if suspicious
        sanitized_query = query
        if input_validation.threat_level == ThreatLevel.SUSPICIOUS:
            sanitized_query = guardrail.sanitize_input(query)

        # Step 1 & 2: Route and Execute (not streamable)
        tasks = await self._router.route(sanitized_query, context, max_tools)

        if not tasks:
            yield "Non ho trovato strumenti appropriati per questa richiesta."
            return

        results = await self._executor.execute(tasks)

        # Step 3: Synthesize with streaming
        # Accumulate answer for post-processing
        full_answer = ""
        async for chunk in self._synthesizer.synthesize_streaming(query, results, context):
            # Handle StreamChunk objects — only yield content, skip thinking
            from me4brain.engine.types import StreamChunk

            if isinstance(chunk, StreamChunk):
                if chunk.type == "content" and chunk.content:
                    full_answer += chunk.content
                    yield chunk.content
                # Skip thinking chunks in this non-SSE path
            elif isinstance(chunk, str):
                full_answer += chunk
                yield chunk
            elif isinstance(chunk, dict) and chunk.get("type") == "content":
                text = chunk.get("content", "")
                if text:
                    full_answer += text
                    yield text

        # Step 3.5: Post-synthesis - Populate empty Google Docs with synthesized content
        if full_answer:
            await self._populate_empty_docs(results, tasks, full_answer, original_query=query)

    async def run_iterative(
        self,
        query: str,
        context: str | None = None,
    ) -> EngineResponse:
        """Full pipeline with ITERATIVE execution (ReAct pattern).

        Instead of sending all tools to LLM at once, this method:
        1. Decomposes query into sub-tasks (planning)
        2. For each sub-task, retrieves only 5-10 relevant tools
        3. Executes tools for that sub-task
        4. Accumulates results and moves to next sub-task
        5. Synthesizes final response from all results

        This avoids provider limits (e.g., NanoGPT 40 tool limit) by
        keeping each LLM call under 10 tools.

        Args:
            query: User's natural language query
            context: Optional additional context

        Returns:
            EngineResponse with answer and tool results
        """
        import time as time_module

        start_time = time_module.monotonic()

        # Step 0: Security - Validate input with guardrail
        from me4brain.engine.guardrail import ThreatLevel, get_guardrail

        guardrail = get_guardrail()
        input_validation = guardrail.validate_input(query)

        if input_validation.threat_level == ThreatLevel.DANGEROUS:
            logger.warning(
                "engine_iterative_input_blocked",
                query_preview=query[:50],
                reason=input_validation.reason,
            )
            return EngineResponse(
                answer="⚠️ La richiesta contiene pattern potenzialmente pericolosi.",
                tool_results=[],
                tools_called=[],
                total_latency_ms=(time_module.monotonic() - start_time) * 1000,
            )

        sanitized_query = query
        if input_validation.threat_level == ThreatLevel.SUSPICIOUS:
            sanitized_query = guardrail.sanitize_input(query)

        use_unified_intent = _should_use_unified_intent(self._config, sanitized_query)
        analysis = None
        if use_unified_intent and self._analyzer is not None:
            analysis = await self._analyzer.analyze(sanitized_query, context)

        analysis_domains = analysis.domains if analysis is not None else []

        if analysis is not None and analysis.intent == IntentType.CONVERSATIONAL:
            logger.info(
                "conversational_query_detected_iterative",
                query_preview=sanitized_query[:50],
                confidence=analysis.confidence,
            )
            from me4brain.llm.models import LLMRequest, Message, MessageRole

            resolved_client, actual_model = resolve_model_client(self._config.model_routing)
            request = LLMRequest(
                messages=[
                    Message(
                        role=MessageRole.SYSTEM,
                        content="Sei un assistente amichevole. Rispondi in italiano in modo conciso.",
                    ),
                    Message(role=MessageRole.USER, content=sanitized_query),
                ],
                model=actual_model,
                temperature=0.7,
            )
            response = await resolved_client.generate_response(request)
            return EngineResponse(
                answer=response.choices[0].message.content
                if response.choices
                else "Ciao! Come posso aiutarti?",
                tool_results=[],
                tools_called=[],
                total_latency_ms=(time_module.monotonic() - start_time) * 1000,
            )

        # Step 1: Check if router supports iterative execution
        if not hasattr(self._router, "retriever") or not hasattr(self._router, "decomposer"):
            logger.warning(
                "iterative_execution_not_supported",
                router_type=type(self._router).__name__,
            )
            # Fallback to standard execution
            return await self.run(query, context)

        # Step 2: Classify and decompose query
        classification, _ = await self._router.classifier.classify_with_fallback(sanitized_query)

        logger.debug(
            "iterative_query_classified",
            domain=classification.domain_names[0] if classification.domain_names else "unknown",
            confidence=classification.confidence,
            intent_analysis_domains=analysis_domains,
        )

        sub_queries = await self._router.decomposer.decompose(sanitized_query, classification)

        if not sub_queries:
            logger.warning(
                "no_sub_queries_generated",
                query_preview=query[:100],
                domain=classification.domain_names[0] if classification.domain_names else "unknown",
            )
            # Fallback to standard execution
            return await self.run(query, context)

        logger.info(
            "iterative_execution_started",
            total_steps=len(sub_queries),
            sub_queries=[sq.text[:50] for sq in sub_queries],
        )

        # Step 3: Create and run IterativeExecutor
        from me4brain.engine.iterative_executor import IterativeExecutor

        iterative_executor = IterativeExecutor(
            llm_client=self._router.llm_client,
            retriever=self._router.retriever,
            executor=self._executor,
        )

        exec_context = await iterative_executor.execute_plan(
            sub_queries=sub_queries,
            original_query=sanitized_query,
            context_str=context,
        )

        # Step 4: Collect all results
        all_results = exec_context.get_all_tool_results()
        all_tasks = exec_context.get_all_tasks()

        if not all_results:
            logger.info(
                "engine_iterative_no_results",
                query_preview=query[:50],
            )
            return EngineResponse(
                answer="Non sono riuscito a eseguire alcuno strumento per questa richiesta.",
                tool_results=[],
                tools_called=[],
                total_latency_ms=(time_module.monotonic() - start_time) * 1000,
            )

        # Step 5: Synthesize final response
        answer = await self._synthesizer.synthesize(query, all_results, context)

        # Post-synthesis: Populate empty Google Docs
        await self._populate_empty_docs(all_results, all_tasks, answer, original_query=query)

        # Security: Validate output
        output_validation = guardrail.validate_output(answer)
        if output_validation.threat_level == ThreatLevel.DANGEROUS:
            answer = guardrail.filter_output(answer)

        total_latency = (time_module.monotonic() - start_time) * 1000

        logger.info(
            "engine_iterative_complete",
            query_preview=query[:50],
            steps_executed=len(exec_context.step_results),
            tools_called=len(all_tasks),
            successful=sum(1 for r in all_results if r.success),
            total_latency_ms=round(total_latency, 2),
        )

        return EngineResponse(
            answer=answer,
            tool_results=all_results,
            tools_called=[t.tool_name for t in all_tasks],
            reasoning_trace=[
                f"Step {sr.step_id}: {getattr(sr, 'sub_query', 'N/A')[:100]}"
                for sr in exec_context.step_results
            ],
            total_latency_ms=total_latency,
        )

    async def run_iterative_stream(
        self,
        query: str,
        context: str | None = None,
        session_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Full pipeline with ITERATIVE execution, yielding SSE progress events.

        Same flow as run_iterative() but yields user-friendly progress events
        for real-time streaming to the frontend.

        Args:
            query: User query
            context: Optional context information
            session_id: Optional session ID for synthesis streaming

        Event types yielded:
            thinking  - System is analyzing the query
            plan      - Sub-queries identified
            step_start / step_complete / step_error - Per-step progress
            synthesizing - Final synthesis in progress
            content   - Chunks of the final answer
            done      - Execution complete
        """
        import time as time_module

        start_time = time_module.monotonic()

        # Step 0: Thinking event
        yield {"type": "thinking", "message": "Sto analizzando la tua richiesta...", "icon": "🔍"}

        # Security guardrail
        from me4brain.engine.guardrail import ThreatLevel, get_guardrail

        guardrail = get_guardrail()
        input_validation = guardrail.validate_input(query)

        if input_validation.threat_level == ThreatLevel.DANGEROUS:
            yield {"type": "error", "message": "La richiesta contiene elementi non sicuri"}
            yield {"type": "done", "tools_count": 0, "latency_ms": 0}
            return

        sanitized_query = query
        if input_validation.threat_level == ThreatLevel.SUSPICIOUS:
            sanitized_query = guardrail.sanitize_input(query)

        # 🎯 NUOVO: Unified Intent Analysis (replaces conversational bypass)
        analysis = await self._analyzer.analyze(sanitized_query, context)

        if analysis.intent == IntentType.CONVERSATIONAL:
            logger.info(
                "conversational_query_detected",
                query_preview=sanitized_query[:50],
                confidence=analysis.confidence,
            )

            # Rispondi direttamente senza tools
            yield {"type": "thinking", "message": "Sto riflettendo...", "icon": "💭"}

            # Use local tool calling client if configured, otherwise router client
            from me4brain.llm.provider_factory import get_tool_calling_client

            conv_client = (
                get_tool_calling_client()
                if self._config.use_local_tool_calling
                else self._router.llm_client
            )

            # Select model based on provider type
            from me4brain.llm.ollama import OllamaClient

            conv_model = (
                self._config.ollama_model
                if isinstance(conv_client, OllamaClient)
                else self._config.model_routing
            )

            from me4brain.llm.models import LLMRequest, Message, MessageRole

            resolved_client, actual_model = resolve_model_client(conv_model)
            request = LLMRequest(
                messages=[
                    Message(
                        role=MessageRole.SYSTEM,
                        content="""Sei un assistente conversazionale amichevole e utile.
Rispondi naturalmente in italiano, senza usare tools o API.
Sii conciso ma completo.""",
                    ),
                    Message(role=MessageRole.USER, content=sanitized_query),
                ],
                model=actual_model,
                temperature=0.7,
                max_tokens=500,
                stream=False,  # ← generate_response() è sempre non-streaming
            )

            try:
                response = await resolved_client.generate_response(request)

                content = ""
                if response.choices and response.choices[0].message.content:
                    content = response.choices[0].message.content
                if not content:
                    content = "Ciao! Come posso aiutarti?"

                # Emetti il contenuto a chunks per il frontend SSE
                for i in range(0, len(content), 80):
                    yield {"type": "content", "content": content[i : i + 80]}

                yield {
                    "type": "done",
                    "tools_count": 0,
                    "tools_called": [],
                    "latency_ms": round((time_module.monotonic() - start_time) * 1000, 2),
                }
                return

            except Exception as e:
                logger.error(
                    "conversational_response_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    model=conv_model,
                    provider=type(conv_client).__name__,
                )
                # 🎯 FIX: Fail-fast invece di silent fallback to tool routing
                # L'errore conversazionale deve essere esplicito, non mascherato
                yield {
                    "type": "error",
                    "message": "Non sono riuscito a generare una risposta conversazionale. Riprova o riformula la domanda.",
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "provider": type(conv_client).__name__,
                    "model": conv_model,
                    "stage": "conversational",
                }
                yield {
                    "type": "done",
                    "tools_count": 0,
                    "tools_called": [],
                    "latency_ms": round((time_module.monotonic() - start_time) * 1000, 2),
                }
                return  # Non continuare con tool routing!

        # Check router support
        if not hasattr(self._router, "retriever") or not hasattr(self._router, "decomposer"):
            # Fallback: yield thinking → run standard → yield content
            yield {"type": "thinking", "message": "Sto elaborando...", "icon": "🔄"}
            result = await self.run(query, context)
            for i in range(0, len(result.answer), 60):
                yield {"type": "content", "content": result.answer[i : i + 60]}
            yield {
                "type": "done",
                "tools_count": len(result.tools_called),
                "latency_ms": round(result.total_latency_ms, 2),
            }
            return

        # Step 1: Classify & decompose (Full routing for non-conversational queries)
        classification, _ = await self._router.classifier.classify_with_fallback(sanitized_query)
        sub_queries = await self._router.decomposer.decompose(sanitized_query, classification)

        if not sub_queries:
            # Fallback
            result = await self.run(query, context)
            for i in range(0, len(result.answer), 60):
                yield {"type": "content", "content": result.answer[i : i + 60]}
            yield {
                "type": "done",
                "tools_count": len(result.tools_called),
                "latency_ms": round(result.total_latency_ms, 2),
            }
            return

        # Step 2: Plan event
        # Build a user-friendly plan description
        domain_labels = {
            "communication": "Email",
            "scheduling": "Calendario",
            "file_management": "Documenti",
            "content_creation": "Creazione documenti",
            "data_analysis": "Analisi dati",
            "finance": "Mercati finanziari",
            "geo_weather": "Meteo",
            "web_search": "Ricerca web",
            "travel": "Viaggi",
            "food": "Ristoranti",
            "entertainment": "Eventi",
            "sports": "Sport",
            "shopping": "Shopping",
        }
        areas = []
        for sq in sub_queries:
            label = domain_labels.get(sq.domain, sq.domain)
            if label not in areas:
                areas.append(label)

        yield {
            "type": "plan",
            "message": f"Ho capito: {len(sub_queries)} attività da completare",
            "icon": "✅",
            "areas": areas,
            "steps_count": len(sub_queries),
        }

        try:
            # Step 3: Execute iteratively with streaming

            iterative_executor = self._iterative_executor
            if iterative_executor is None:
                from me4brain.engine.iterative_executor import IterativeExecutor
                from me4brain.llm.provider_factory import get_tool_calling_client

                # ✅ FIX: Use specialized tool-calling client for streaming path
                tc_client = (
                    get_tool_calling_client()
                    if self._config.use_local_tool_calling
                    else self._router.llm_client
                )
                from me4brain.llm.ollama import OllamaClient

                tc_model = (
                    self._config.ollama_model
                    if isinstance(tc_client, OllamaClient)
                    else self._config.model_routing
                )

                iterative_executor = IterativeExecutor(
                    llm_client=self._router.llm_client,
                    retriever=self._router.retriever,
                    executor=self._executor,
                    model=self._config.model_routing,
                    tool_calling_llm=tc_client,  # ✅ FIX: Pass tool-calling LLM
                    tool_calling_model=tc_model,  # ✅ FIX: Pass tool-calling model
                )

            start_time = time.time()
            exec_context = None
            async for event in iterative_executor.execute_plan_stream(
                sub_queries=sub_queries,
                original_query=sanitized_query,
                context_str=context,
            ):
                if event["type"] == "execution_done":
                    exec_context = event["exec_context"]
                else:
                    yield event

            execution_time = time.time() - start_time
            logger.info("iterative_execution_complete", duration_ms=int(execution_time * 1000))

            if exec_context is None:
                yield {"type": "error", "message": "Errore nell'esecuzione"}
                # The finally block will handle the 'done' event
                return

            # Step 4: Collect results
            all_results = exec_context.get_all_tool_results()
            all_tasks = exec_context.get_all_tasks()

            if not all_results:
                yield {
                    "type": "content",
                    "content": "Operazione completata. Non sono stati necessari strumenti aggiuntivi o non sono stati trovati risultati specifici.",
                }
                # The finally block will handle the 'done' event
                return

            # Step 5: Synthesize con streaming
            yield {"type": "synthesizing", "message": "Sto preparando la risposta...", "icon": "💬"}

            full_answer = ""
            total_thinking_sent = 0  # DEBUG: Track total thinking length
            async for synthesis_event in self._synthesizer.synthesize_streaming(
                query, all_results, context, session_id=session_id
            ):
                # Handle StreamChunk objects or dicts
                from me4brain.engine.types import StreamChunk

                if isinstance(synthesis_event, StreamChunk):
                    event_type = synthesis_event.type
                    # Use .thinking field first (native reasoning), fallback to .content
                    thinking_text = synthesis_event.thinking or synthesis_event.content
                    content_text = synthesis_event.content
                    phase = synthesis_event.phase
                elif isinstance(synthesis_event, dict):
                    event_type = synthesis_event.get("type")
                    thinking_text = synthesis_event.get("thinking") or synthesis_event.get(
                        "content"
                    )
                    content_text = synthesis_event.get("content")
                    phase = synthesis_event.get("phase")
                else:
                    continue

                # Propaga thinking dal LLM come evento separato per il frontend
                if event_type == "thinking":
                    if thinking_text:
                        total_thinking_sent += len(thinking_text)
                        yield {
                            "type": "thinking",
                            "content": thinking_text,
                            "phase": phase or "synthesis",
                            "icon": "🤔",
                        }
                elif event_type == "content" and content_text:
                    full_answer += content_text
                    yield {"type": "content", "content": content_text}

            # DEBUG: Log total thinking sent
            logger.info(
                "streaming_thinking_complete",
                total_thinking_chars=total_thinking_sent,
                query_preview=query[:50],
            )

            answer = full_answer

            # Post-synthesis: Populate empty docs
            await self._populate_empty_docs(
                all_results, all_tasks, answer, original_query=sanitized_query
            )

            # Security output validation
            output_validation = guardrail.validate_output(answer)
            if output_validation.threat_level == ThreatLevel.DANGEROUS:
                answer = guardrail.filter_output(answer)

        except Exception as e:
            logger.error("iterative_stream_error", error=str(e))
            yield {"type": "error", "error": str(e)}
            all_tasks = []  # Ensure all_tasks is defined for finally block

        finally:
            total_latency = (time_module.monotonic() - start_time) * 1000
            # Step 7: Done
            yield {
                "type": "done",
                "tools_count": len(all_tasks) if "all_tasks" in locals() else 0,
                "tools_called": [t.tool_name for t in all_tasks] if "all_tasks" in locals() else [],
                "latency_ms": round(total_latency, 2),
            }

        logger.info(
            "engine_iterative_stream_complete",
            query_preview=query[:50],
            steps_executed=len(exec_context.step_results),
            tools_called=len(all_tasks),
            total_latency_ms=round(total_latency, 2),
        )

    async def route(
        self,
        query: str,
        context: str | None = None,
        max_tools: int = 100,
    ) -> list[ToolTask]:
        """Only routing - get tool tasks without execution.

        Useful for debugging or custom execution logic.

        Args:
            query: User query
            context: Optional context
            max_tools: Maximum tools

        Returns:
            List of ToolTask objects
        """
        return await self._router.route(query, context, max_tools)

    async def execute_tasks(
        self,
        tasks: list[ToolTask],
    ) -> list[ToolResult]:
        """Execute pre-defined tasks without routing.

        Args:
            tasks: List of ToolTask objects

        Returns:
            List of ToolResult objects
        """
        return await self._executor.execute(tasks)

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Execute a specific tool directly.

        Bypasses routing entirely for direct tool access.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        return await self._executor.execute_direct(tool_name, arguments)

    @classmethod
    async def _register_skill_handlers(
        cls,
        catalog: ToolCatalog,
    ) -> int:
        """Register skill executors from SkillRegistry into ToolCatalog.

        This enables skills (SKILL.md files) to be executed like regular Python tools.

        Args:
            catalog: ToolCatalog to register skill handlers into

        Returns:
            Number of skills registered
        """
        try:
            logger.info(
                "skill_registration_attempting",
                message="Starting skill handler registration",
            )

            from me4brain.engine.types import ToolDefinition, ToolParameter
            from me4brain.skills import SkillLoader, SkillRegistry
            from me4brain.skills.executor import create_skill_executor

            # Load skills
            loader = SkillLoader()
            registry = SkillRegistry(loader)
            await registry.initialize()

            logger.info(
                "skill_registration_starting",
                total_skills=len(registry.skills),
                skill_names=[s.metadata.name for s in registry.skills[:10]],  # First 10
            )

            registered = 0

            # Use all discovered skills (not just ready_skills) since status defaults to DISCOVERED
            for skill in registry.skills:
                try:
                    # Use skill name directly (e.g., "ebay-search")
                    tool_name = skill.metadata.name

                    # Create executor for this skill
                    executor = create_skill_executor(skill)

                    # Create tool definition for the skill
                    tool_def = ToolDefinition(
                        name=tool_name,
                        description=skill.description,
                        domain="shopping"
                        if any(
                            t in skill.metadata.tags
                            for t in [
                                "shopping",
                                "marketplace",
                                "ebay",
                                "subito",
                                "vinted",
                                "wallapop",
                            ]
                        )
                        else "utility",
                        parameters={
                            "query": ToolParameter(
                                type="string",
                                description="Search query or input for this skill",
                                required=True,
                            ),
                        },
                    )

                    # Register in catalog
                    catalog.register(tool_def, executor)
                    registered += 1

                    logger.debug(
                        "skill_handler_registered",
                        skill_name=tool_name,
                        domain=tool_def.domain,
                    )

                except Exception as e:
                    logger.warning(
                        "skill_handler_registration_failed",
                        skill_name=skill.metadata.name if hasattr(skill, "metadata") else "unknown",
                        error=str(e),
                    )

            return registered

        except ImportError as e:
            logger.debug("skills_module_not_available", error=str(e))
            return 0
        except Exception as e:
            logger.warning("skill_handlers_registration_error", error=str(e))
            return 0

    @property
    def catalog(self) -> ToolCatalog:
        """Get the tool catalog."""
        return self._catalog

    def get_available_tools(self) -> list[str]:
        """Get list of available tool names."""
        return [t.name for t in self._catalog.get_all_tools()]

    def get_tools_by_domain(self, domain: str) -> list[str]:
        """Get tool names filtered by domain."""
        return [t.name for t in self._catalog.get_tools_by_domain(domain)]


# Module-level singleton for convenience
_engine_instance: ToolCallingEngine | None = None


async def get_engine() -> ToolCallingEngine:
    """Get or create the global engine instance.

    Returns:
        Shared ToolCallingEngine instance
    """
    global _engine_instance

    if _engine_instance is None:
        _engine_instance = await ToolCallingEngine.create()

    return _engine_instance


async def reset_engine() -> None:
    """Reset the global engine instance.

    Forces re-creation on next get_engine() call.
    Useful for testing or after configuration changes.
    """
    global _engine_instance
    _engine_instance = None
