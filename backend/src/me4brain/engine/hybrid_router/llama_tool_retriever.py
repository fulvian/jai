"""LlamaIndex Tool Retriever - Two-stage retrieval con reranking.

Sostituisce il ToolRetriever manuale con:
- Stage 1: Coarse retrieval via Qdrant vector search + domain filtering
- Stage 2: Fine-grained reranking con LLM
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from llama_index.core.postprocessor import LLMRerank
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores.types import (
    FilterCondition,
    MetadataFilter,
    MetadataFilters,
)

from me4brain.engine.hybrid_router.tool_index import ToolIndexManager
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    HybridRouterConfig,
    RetrievedTool,
    SubQuery,
    ToolRetrievalResult,
)
from me4brain.llm.llamaindex_adapter import get_llamaindex_llm

logger = structlog.get_logger(__name__)


class LlamaIndexToolRetriever:
    """Tool retrieval using LlamaIndex VectorStore + LLM Reranking.

    Two-stage retrieval:
    1. Coarse: Vector search with domain metadata filtering
    2. Fine: LLM-based reranking for precision
    """

    def __init__(
        self,
        tool_index: ToolIndexManager,
        config: HybridRouterConfig | None = None,
        tool_schemas_map: dict[str, dict] | None = None,
    ) -> None:
        """Initialize LlamaIndex-based tool retriever.

        Args:
            tool_index: ToolIndexManager instance with built index
            config: Router configuration
            tool_schemas_map: Dict mapping tool_name -> OpenAI-compatible schema
                              Used to enrich tool results since Qdrant only stores metadata.
        """
        self._tool_index = tool_index
        self._config = config or HybridRouterConfig()
        self._reranker: LLMRerank | None = None
        self._tool_schemas_map = tool_schemas_map or {}

    async def initialize(self) -> None:
        """Initialize reranker with LLM."""
        if self._config.use_llm_reranker:
            try:
                llm = get_llamaindex_llm(self._config.reranker_model)
                self._reranker = LLMRerank(
                    llm=llm,
                    top_n=self._config.rerank_top_n,
                    choice_batch_size=5,  # Process in batches for efficiency
                )
                logger.info(
                    "llm_reranker_initialized",
                    model=self._config.reranker_model,
                    top_n=self._config.rerank_top_n,
                )
            except Exception as e:
                logger.warning("llm_reranker_init_failed", error=str(e))
                self._reranker = None

    async def retrieve(
        self,
        query: str,
        classification: DomainClassification,
    ) -> ToolRetrievalResult:
        """Retrieve relevant tools for a query based on classification.

        Uses two-stage retrieval:
        1. Coarse vector search with domain filtering
        2. LLM reranking for precision

        Args:
            query: User query
            classification: Domain classification from Stage 1

        Returns:
            ToolRetrievalResult with selected tools
        """
        if not classification.domains:
            logger.info("no_domains_for_retrieval", query_preview=query[:50])
            return ToolRetrievalResult(tools=[], domains_searched=[])

        index = self._tool_index.index
        if index is None:
            logger.error("tool_index_not_initialized")
            return ToolRetrievalResult(tools=[], domains_searched=[])

        # Extract domain names for filtering
        domain_names = [d.name for d in classification.domains]

        # Build domain filter for Qdrant
        domain_filter = self._build_domain_filter(domain_names)

        # Stage 1: Coarse retrieval with domain filtering
        retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=self._config.coarse_top_k,
            filters=domain_filter,
        )

        try:
            nodes = await retriever.aretrieve(query)
        except Exception as e:
            logger.error("coarse_retrieval_failed", error=str(e))
            return ToolRetrievalResult(tools=[], domains_searched=domain_names)

        logger.debug(
            "coarse_retrieval_complete",
            query_preview=query[:50],
            candidates=len(nodes),
            domains=domain_names,
        )

        # Stage 2: LLM Reranking (if enabled and available)
        if self._reranker and len(nodes) > 0:
            try:
                # Wrap reranking with timeout protection (45 seconds)
                # LLM reranking can be expensive, but should complete in <45 seconds
                try:
                    # Create a callable wrapper for the sync method
                    def _run_reranking():
                        return self._reranker.postprocess_nodes(
                            nodes,
                            query_str=query,
                        )

                    nodes = await asyncio.wait_for(
                        asyncio.to_thread(_run_reranking),
                        timeout=600.0,  # 600 second timeout (development)
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "reranking_timeout",
                        timeout_seconds=600,
                        query_preview=query[:50],
                        fallback="using_unreranked_nodes",
                    )
                    # Continue with unreranked nodes on timeout

                logger.debug(
                    "reranking_complete",
                    reranked_count=len(nodes),
                )
            except Exception as e:
                logger.warning("reranking_failed", error=str(e))
                # Continue with unreranked nodes

        # Convert nodes to RetrievedTool format
        all_retrieved = self._nodes_to_tools(nodes)

        # Apply payload limit
        final_tools, total_bytes = self._fit_to_payload_limit(all_retrieved)

        logger.info(
            "tool_retrieval_complete",
            query_preview=query[:50],
            domains_searched=domain_names,
            tools_before_limit=len(all_retrieved),
            tools_after_limit=len(final_tools),
            total_payload_bytes=total_bytes,
        )

        return ToolRetrievalResult(
            tools=final_tools,
            total_payload_bytes=total_bytes,
            domains_searched=domain_names,
        )

    async def get_tool_by_name(self, name: str) -> RetrievedTool | None:
        """Get a specific tool by name from the schema map.

        Args:
            name: Tool name

        Returns:
            RetrievedTool object or None if not found
        """
        schema = self._tool_schemas_map.get(name)
        if not schema:
            return None

        metadata = schema.get("function", {}).get("metadata", {})

        return RetrievedTool(
            name=name,
            domain=metadata.get("domain", "unknown"),
            similarity_score=1.0,  # Explicitly requested
            schema=schema,
            category=metadata.get("category", ""),
            skill=metadata.get("skill", ""),
        )

    def _build_domain_filter(self, domains: list[str]) -> MetadataFilters:
        """Build Qdrant metadata filter for domain-based filtering."""
        if len(domains) == 1:
            return MetadataFilters(
                filters=[
                    MetadataFilter(key="domain", value=domains[0]),
                ],
            )

        # Multiple domains: OR condition
        return MetadataFilters(
            filters=[MetadataFilter(key="domain", value=domain) for domain in domains],
            condition=FilterCondition.OR,
        )

    def _nodes_to_tools(self, nodes: list[NodeWithScore]) -> list[RetrievedTool]:
        """Convert LlamaIndex nodes to RetrievedTool format.

        Filters tools below min_similarity_score threshold.
        Extracts hierarchical metadata (category, skill) from nodes.
        Now extracts schema directly from payload (schema_json field).
        """
        tools = []
        min_score = self._config.min_similarity_score

        for node in nodes:
            # Use node score as similarity (normalized by LlamaIndex)
            similarity = node.score if node.score is not None else 0.0

            # Filter low similarity tools to avoid false positives
            if similarity < min_score:
                continue

            metadata = node.node.metadata
            tool_name = metadata.get("tool_name", "") or metadata.get("name", "")
            domain = metadata.get("domain", "unknown")
            category = metadata.get("category", "")
            skill = metadata.get("skill", "")

            # Get schema from payload (schema_json field) - NEW approach
            # Falls back to external map only if schema_json is not available
            schema_json = metadata.get("schema_json", "{}")
            schema = {}

            if schema_json:
                try:
                    schema = json.loads(schema_json)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(
                        "invalid_schema_json",
                        tool_name=tool_name,
                        error=str(e),
                    )

            # Fallback to external map if no schema in payload
            if not schema and self._tool_schemas_map:
                schema = self._tool_schemas_map.get(tool_name, {})

            # Log warning if still no schema (not silent skip anymore)
            if not schema:
                logger.warning(
                    "tool_missing_schema",
                    tool_name=tool_name,
                    domain=domain,
                )
                continue

            tools.append(
                RetrievedTool(
                    name=tool_name,
                    domain=domain,
                    similarity_score=similarity,
                    schema=schema,
                    category=category,
                    skill=skill,
                )
            )

        return tools

    def _get_schema_size(self, tool: RetrievedTool) -> int:
        """Get size of tool schema in bytes."""
        return len(json.dumps(tool.schema))

    def _fit_to_payload_limit(
        self,
        tools: list[RetrievedTool],
    ) -> tuple[list[RetrievedTool], int]:
        """Ensure tools fit within payload byte limit.

        Keeps highest similarity tools while respecting byte limit.

        Returns:
            Tuple of (selected_tools, total_bytes)
        """
        max_bytes = self._config.max_payload_bytes
        selected: list[RetrievedTool] = []
        total_bytes = 0

        for tool in tools:
            tool_bytes = self._get_schema_size(tool)

            if total_bytes + tool_bytes <= max_bytes:
                selected.append(tool)
                total_bytes += tool_bytes
            else:
                logger.debug(
                    "tool_excluded_payload_limit",
                    tool=tool.name,
                    tool_bytes=tool_bytes,
                    current_total=total_bytes,
                    max_bytes=max_bytes,
                )

        return selected, total_bytes

    async def retrieve_global_topk(
        self,
        query: str,
        k: int = 25,
    ) -> ToolRetrievalResult:
        """Retrieve top-K tools globally across all domains.

        Used as fallback when domain classification fails or confidence is low.

        Args:
            query: User query
            k: Maximum number of tools to retrieve

        Returns:
            ToolRetrievalResult with top-K tools
        """
        index = self._tool_index.index
        if index is None:
            logger.error("tool_index_not_initialized")
            return ToolRetrievalResult(tools=[], domains_searched=[])

        # Global retrieval without domain filter
        retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=k,
        )

        try:
            nodes = await retriever.aretrieve(query)
        except Exception as e:
            logger.error("global_retrieval_failed", error=str(e))
            return ToolRetrievalResult(tools=[], domains_searched=[])

        # Rerank if available
        if self._reranker and len(nodes) > 0:
            try:
                nodes = self._reranker.postprocess_nodes(nodes, query_str=query)
            except Exception:
                pass  # Use unreranked

        all_tools = self._nodes_to_tools(nodes)
        final_tools, total_bytes = self._fit_to_payload_limit(all_tools)

        domains_found = list(set(t.domain for t in final_tools))

        logger.info(
            "global_topk_retrieval_complete",
            query_preview=query[:50],
            k=k,
            tools_selected=len(final_tools),
            domains_found=domains_found,
            total_payload_bytes=total_bytes,
        )

        return ToolRetrievalResult(
            tools=final_tools,
            total_payload_bytes=total_bytes,
            domains_searched=domains_found,
        )

    async def retrieve_multi_intent(
        self,
        sub_queries: list[SubQuery],
        classification: DomainClassification,
        original_query: str = "",
    ) -> ToolRetrievalResult:
        """Retrieve tools for multiple sub-queries and merge with RRF.

        Multi-intent retrieval strategy:
        1. Execute retrieval for each sub-query (single-domain filtered)
        2. Merge results using Reciprocal Rank Fusion (RRF)
        3. Apply LLM reranking on merged results using ORIGINAL query (if enabled)

        Args:
            sub_queries: List of atomic sub-queries (from QueryDecomposer)
            classification: Original domain classification (for fallback)
            original_query: The user's original query for reranking context

        Returns:
            ToolRetrievalResult with merged tools from all intents
        """
        if not sub_queries:
            logger.warning("no_sub_queries_for_retrieval")
            return ToolRetrievalResult(tools=[], domains_searched=[])

        index = self._tool_index.index
        if index is None:
            logger.error("tool_index_not_initialized")
            return ToolRetrievalResult(tools=[], domains_searched=[])

        # Collect results from each sub-query
        all_results: list[list[RetrievedTool]] = []
        domains_searched: set[str] = set()

        for sq in sub_queries:
            # Build single-domain filter for this sub-query
            domain_filter = self._build_domain_filter([sq.domain])
            domains_searched.add(sq.domain)

            retriever = VectorIndexRetriever(
                index=index,
                similarity_top_k=self._config.coarse_top_k,
                filters=domain_filter,
            )

            try:
                nodes = await retriever.aretrieve(sq.text)
                tools = self._nodes_to_tools(nodes)

                # FALLBACK: If sub-query yields 0 tools and we have original query,
                # retry with original query filtered by this domain
                # Best practice per Perplexity research: sub-queries can be too specific
                if len(tools) == 0 and original_query:
                    logger.debug(
                        "sub_query_fallback_to_original",
                        sub_query=sq.text[:40],
                        domain=sq.domain,
                    )
                    fallback_nodes = await retriever.aretrieve(original_query)
                    tools = self._nodes_to_tools(fallback_nodes)
                    logger.debug(
                        "fallback_retrieval_complete",
                        domain=sq.domain,
                        tools_found=len(tools),
                    )

                all_results.append(tools)

                logger.debug(
                    "sub_query_retrieval_complete",
                    sub_query=sq.text[:40],
                    domain=sq.domain,
                    tools_found=len(tools),
                )
            except Exception as e:
                logger.warning(
                    "sub_query_retrieval_failed",
                    sub_query=sq.text[:40],
                    error=str(e),
                )
                all_results.append([])

        # Merge results with RRF
        merged_tools = self._rrf_merge(all_results)

        logger.info(
            "multi_intent_retrieval_complete",
            sub_query_count=len(sub_queries),
            domains_searched=list(domains_searched),
            tools_before_merge=sum(len(r) for r in all_results),
            tools_after_merge=len(merged_tools),
        )

        # Optional: LLM reranking on merged results using ORIGINAL query
        # Best practice: Rerank after RRF using user's original query for context
        if self._reranker and len(merged_tools) > 0:
            try:
                # Use original query for reranking - best practice per Perplexity research
                # Fallback to concatenating sub-queries if original not provided
                rerank_query = (
                    original_query
                    if original_query
                    else " ".join(sq.text for sq in sub_queries[:2])
                )

                # Create pseudo-nodes for reranking
                from llama_index.core.schema import TextNode, NodeWithScore

                nodes = [
                    NodeWithScore(
                        node=TextNode(
                            text=f"Tool: {t.name}\n{t.schema.get('function', {}).get('description', '')}",
                            metadata={"tool_name": t.name, "domain": t.domain},
                        ),
                        score=t.similarity_score,
                    )
                    for t in merged_tools[: self._config.coarse_top_k]
                ]
                reranked = self._reranker.postprocess_nodes(nodes, query_str=rerank_query)
                # Rebuild tool list from reranked nodes
                reranked_names = [n.node.metadata.get("tool_name") for n in reranked]
                merged_tools = [
                    t for name in reranked_names for t in merged_tools if t.name == name
                ][: self._config.rerank_top_n]
            except Exception as e:
                logger.warning("multi_intent_reranking_failed", error=str(e))

        # Apply payload limit
        final_tools, total_bytes = self._fit_to_payload_limit(merged_tools)

        return ToolRetrievalResult(
            tools=final_tools,
            total_payload_bytes=total_bytes,
            domains_searched=list(domains_searched),
        )

    def _rrf_merge(
        self,
        result_lists: list[list[RetrievedTool]],
        k: int = 60,
    ) -> list[RetrievedTool]:
        """Merge multiple retrieval results using Weighted Reciprocal Rank Fusion.

        Weighted RRF formula: score(d) = Σ (weight * 1 / (k + rank(d)))
        where:
        - k is a constant (default 60) for rank smoothing
        - weight is based on tool type: static tools (0.95), crystallized (0.75), learned (0.60)

        This prioritizes verified static tools over user-created skills.

        Args:
            result_lists: List of tool lists from different sub-queries
            k: RRF constant (higher = more weight to lower ranks)

        Returns:
            Merged and deduplicated tool list, sorted by weighted RRF score
        """
        # Priority weights based on tool type
        WEIGHT_STATIC = 0.95  # Curated Python tools
        WEIGHT_CRYSTALLIZED = 0.75  # User-verified skills
        WEIGHT_LEARNED = 0.60  # Auto-generated skills

        rrf_scores: dict[str, float] = {}
        tool_by_name: dict[str, RetrievedTool] = {}

        for result_list in result_lists:
            for rank, tool in enumerate(result_list, start=1):
                # Determine weight based on tool schema metadata
                schema = tool.schema
                func = schema.get("function", {}) if schema else {}

                # Check if it's a static tool or skill
                # Skills have "skill_id" in metadata, static tools don't
                if "skill_id" not in func.get("metadata", {}):
                    weight = WEIGHT_STATIC
                else:
                    # Check skill subtype: crystallized vs learned
                    subtype = func.get("metadata", {}).get("subtype", "learned")
                    weight = WEIGHT_CRYSTALLIZED if subtype == "crystallized" else WEIGHT_LEARNED

                # Weighted RRF score contribution
                rrf_scores[tool.name] = rrf_scores.get(tool.name, 0) + (weight * 1 / (k + rank))

                # Keep the highest similarity score for each tool
                if (
                    tool.name not in tool_by_name
                    or tool.similarity_score > tool_by_name[tool.name].similarity_score
                ):
                    tool_by_name[tool.name] = tool

        # Sort by weighted RRF score descending
        sorted_names = sorted(rrf_scores.keys(), key=lambda n: rrf_scores[n], reverse=True)

        return [tool_by_name[name] for name in sorted_names]
