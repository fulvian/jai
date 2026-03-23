"""Stage 2: Tool Retrieval via Embeddings.

Retrieves relevant tools using semantic similarity based on query embeddings.
Uses dynamic threshold instead of fixed K for flexible tool selection.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import structlog

from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    HybridRouterConfig,
    RetrievedTool,
    ToolRetrievalResult,
)

logger = structlog.get_logger(__name__)


class ToolRetriever:
    """Retrieves tools using embedding similarity.

    Stage 2 of the hybrid router - uses embeddings to find the most
    relevant tools for a query within specified domains.
    """

    def __init__(
        self,
        tool_schemas: dict[str, dict[str, Any]],
        tool_embeddings: dict[str, np.ndarray],
        tool_domains: dict[str, str],
        embed_fn: callable,
        config: HybridRouterConfig | None = None,
    ) -> None:
        """Initialize tool retriever.

        Args:
            tool_schemas: Dict mapping tool_name -> OpenAI tool schema
            tool_embeddings: Dict mapping tool_name -> embedding vector
            tool_domains: Dict mapping tool_name -> domain name
            embed_fn: Async function to embed queries
            config: Router configuration
        """
        self._schemas = tool_schemas
        self._embeddings = tool_embeddings
        self._domains = tool_domains
        self._embed_fn = embed_fn
        self._config = config or HybridRouterConfig()

        # Group tools by domain for efficient lookup
        self._tools_by_domain: dict[str, list[str]] = {}
        for tool_name, domain in tool_domains.items():
            if domain not in self._tools_by_domain:
                self._tools_by_domain[domain] = []
            self._tools_by_domain[domain].append(tool_name)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _get_schema_size(self, tool_name: str) -> int:
        """Get size of tool schema in bytes."""
        schema = self._schemas.get(tool_name, {})
        return len(json.dumps(schema))

    async def retrieve(
        self,
        query: str,
        classification: DomainClassification,
    ) -> ToolRetrievalResult:
        """Retrieve relevant tools for a query based on classification.

        Uses dynamic threshold based on complexity instead of fixed K.

        Args:
            query: User query
            classification: Domain classification from Stage 1

        Returns:
            ToolRetrievalResult with selected tools
        """
        if not classification.domains:
            logger.info("no_domains_for_retrieval", query_preview=query[:50])
            return ToolRetrievalResult(tools=[], domains_searched=[])

        # Embed the query
        query_embedding = await self._embed_fn(query)

        all_retrieved: list[RetrievedTool] = []
        domains_searched: list[str] = []

        for domain_info in classification.domains:
            domain = domain_info.name
            complexity = domain_info.complexity

            if domain not in self._tools_by_domain:
                logger.warning("unknown_domain", domain=domain)
                continue

            domains_searched.append(domain)

            # Get threshold based on complexity
            threshold = self._config.similarity_thresholds.get(complexity, 0.6)

            # Retrieve tools above threshold, but keep track of best tool for this domain
            domain_tools = self._tools_by_domain[domain]
            best_tool_in_domain: RetrievedTool | None = None
            max_sim_in_domain = -1.0
            found_above_threshold = False

            for tool_name in domain_tools:
                if tool_name not in self._embeddings:
                    continue

                tool_embedding = self._embeddings[tool_name]
                similarity = self._cosine_similarity(query_embedding, tool_embedding)

                retrieved = RetrievedTool(
                    name=tool_name,
                    domain=domain,
                    similarity_score=similarity,
                    schema=self._schemas.get(tool_name, {}),
                )

                if similarity > max_sim_in_domain:
                    max_sim_in_domain = similarity
                    best_tool_in_domain = retrieved

                if similarity >= threshold:
                    all_retrieved.append(retrieved)
                    found_above_threshold = True

            # FALLBACK: If no tools found above threshold for this classified domain,
            # include the best one IF it exceeds absolute floor (0.40)
            # This prevents including irrelevant tools just because they're "best in domain"
            FALLBACK_FLOOR = 0.40  # Absolute minimum - never include tools below this
            if not found_above_threshold and best_tool_in_domain:
                if best_tool_in_domain.similarity_score >= FALLBACK_FLOOR:
                    all_retrieved.append(best_tool_in_domain)
                    logger.info(
                        "force_included_best_tool_for_domain",
                        domain=domain,
                        tool=best_tool_in_domain.name,
                        score=max_sim_in_domain,
                        threshold=threshold,
                    )
                else:
                    # Tool rejected - too low similarity, would confuse LLM
                    logger.warning(
                        "fallback_rejected_low_similarity",
                        domain=domain,
                        tool=best_tool_in_domain.name,
                        score=max_sim_in_domain,
                        floor=FALLBACK_FLOOR,
                    )

        # Sort by similarity score (best first)
        all_retrieved.sort(key=lambda t: t.similarity_score, reverse=True)

        # Check payload size and trim if needed
        final_tools, total_bytes = self._fit_to_payload_limit(all_retrieved)

        logger.info(
            "tool_retrieval_complete",
            query_preview=query[:50],
            domains_searched=domains_searched,
            tools_before_limit=len(all_retrieved),
            tools_after_limit=len(final_tools),
            total_payload_bytes=total_bytes,
        )

        return ToolRetrievalResult(
            tools=final_tools,
            total_payload_bytes=total_bytes,
            domains_searched=domains_searched,
        )

    async def get_tool_by_name(self, name: str) -> RetrievedTool | None:
        """Get a specific tool by name from the schema map.

        Args:
            name: Tool name

        Returns:
            RetrievedTool object or None if not found
        """
        schema = self._schemas.get(name)
        if not schema:
            return None

        domain = self._domains.get(name, "unknown")

        return RetrievedTool(
            name=name,
            domain=domain,
            similarity_score=1.0,  # Explicitly requested
            schema=schema,
        )

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
            tool_bytes = self._get_schema_size(tool.name)

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
        query_embedding = await self._embed_fn(query)

        all_tools: list[RetrievedTool] = []

        for tool_name, tool_embedding in self._embeddings.items():
            similarity = self._cosine_similarity(query_embedding, tool_embedding)
            domain = self._domains.get(tool_name, "unknown")

            all_tools.append(
                RetrievedTool(
                    name=tool_name,
                    domain=domain,
                    similarity_score=similarity,
                    schema=self._schemas.get(tool_name, {}),
                )
            )

        # Sort by similarity and take top-K
        all_tools.sort(key=lambda t: t.similarity_score, reverse=True)
        top_k = all_tools[:k]

        # Ensure within payload limit
        final_tools, total_bytes = self._fit_to_payload_limit(top_k)

        domains_searched = list(set(t.domain for t in final_tools))

        logger.info(
            "global_topk_retrieval_complete",
            query_preview=query[:50],
            k=k,
            tools_selected=len(final_tools),
            domains_found=domains_searched,
            total_payload_bytes=total_bytes,
        )

        return ToolRetrievalResult(
            tools=final_tools,
            total_payload_bytes=total_bytes,
            domains_searched=domains_searched,
        )


class ToolEmbeddingManager:
    """Manages tool embeddings for the retriever.

    Handles initial embedding computation and updates when tools change.
    """

    def __init__(self, embed_fn: callable) -> None:
        self._embed_fn = embed_fn
        self._embeddings: dict[str, np.ndarray] = {}
        self._tool_domains: dict[str, str] = {}
        self._tool_schemas: dict[str, dict[str, Any]] = {}

    async def compute_embeddings(
        self,
        tool_schemas: list[dict[str, Any]],
    ) -> None:
        """Compute embeddings for all tools.

        Should be called at startup to pre-compute embeddings.

        Args:
            tool_schemas: List of OpenAI-compatible tool schemas
        """
        logger.info("computing_tool_embeddings", tool_count=len(tool_schemas))

        for schema in tool_schemas:
            func = schema.get("function", {})
            tool_name = func.get("name", "")
            description = func.get("description", "")

            if not tool_name or not description:
                continue

            # Create embedding text from name + description
            embed_text = f"{tool_name}: {description}"
            embedding = await self._embed_fn(embed_text)

            self._embeddings[tool_name] = np.array(embedding)
            self._tool_schemas[tool_name] = schema

            # Extract domain from schema metadata if available
            # (domain should be stored in the catalog)

        logger.info(
            "tool_embeddings_computed",
            embedded_count=len(self._embeddings),
        )

    def set_domains(self, tool_domains: dict[str, str]) -> None:
        """Set domain mappings for tools."""
        self._tool_domains = tool_domains

    def get_embeddings(self) -> dict[str, np.ndarray]:
        """Get computed embeddings."""
        return self._embeddings

    def get_schemas(self) -> dict[str, dict[str, Any]]:
        """Get tool schemas."""
        return self._tool_schemas

    def get_domains(self) -> dict[str, str]:
        """Get tool domain mappings."""
        return self._tool_domains

    async def update_tool(
        self,
        tool_name: str,
        schema: dict[str, Any],
        domain: str,
    ) -> None:
        """Update or add a single tool embedding.

        Used when a new skill is created or a tool is modified.
        """
        func = schema.get("function", {})
        description = func.get("description", "")

        if description:
            embed_text = f"{tool_name}: {description}"
            embedding = await self._embed_fn(embed_text)

            self._embeddings[tool_name] = np.array(embedding)
            self._tool_schemas[tool_name] = schema
            self._tool_domains[tool_name] = domain

            logger.info("tool_embedding_updated", tool=tool_name, domain=domain)
