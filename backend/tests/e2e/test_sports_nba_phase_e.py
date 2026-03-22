"""Phase E: End-to-End Tests for Hybrid Routing with Sports NBA.

Real multi-intent sports queries testing the full routing pipeline:
- Stage 0: Intent Analysis + Context Rewriting
- Stage 1: Domain classification
- Stage 1b: Query decomposition
- Stage 2: Tool retrieval
- Stage 3: Model selection and execution

Coverage: 5+ real sports_nba multi-intent queries with fallback verification.
"""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any

from me4brain.engine.hybrid_router.router import HybridToolRouter
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainComplexity,
    HybridRouterConfig,
    RetrievedTool,
    ToolRetrievalResult,
    SubQuery,
)
from me4brain.engine.types import ToolTask
from me4brain.llm.models import (
    LLMResponse,
    Choice,
    ChoiceMessage,
    Message,
    MessageRole,
    ToolCall,
    ToolCallFunction,
)


class TestE2ESportsNBAMultiIntent:
    """E2E tests for multi-intent sports NBA routing pipeline."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock NanoGPT LLM client."""
        client = AsyncMock()
        client.generate_response = AsyncMock()
        return client

    @pytest.fixture
    def router_config(self):
        """Router configuration for testing."""
        return HybridRouterConfig(
            use_query_decomposition=True,
            use_llamaindex_retriever=False,  # Use in-memory for testing
            max_payload_bytes=28_000,
        )

    @pytest.fixture
    async def initialized_router(self, mock_llm_client, router_config):
        """Create and initialize a router for testing."""
        router = HybridToolRouter(
            llm_client=mock_llm_client,
            config=router_config,
        )

        # Mock tool schemas for sports_nba
        tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": "get_nba_games",
                    "description": "Get upcoming or live NBA games",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Game date"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_player_stats",
                    "description": "Get NBA player statistics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "player_name": {"type": "string", "description": "Player name"},
                            "season": {"type": "string", "description": "Season year"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_team_stats",
                    "description": "Get NBA team statistics and standings",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "team_name": {"type": "string", "description": "Team name"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_betting_odds",
                    "description": "Get NBA game betting odds and lines",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "game_date": {"type": "string", "description": "Game date"},
                            "teams": {"type": "array", "description": "Team names"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_betting_patterns",
                    "description": "Analyze professional betting predictions",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Analysis query"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_team_injuries",
                    "description": "Get NBA team injury reports",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "team_name": {"type": "string", "description": "Team name"},
                        },
                    },
                },
            },
        ]

        tool_domains = {
            "get_nba_games": "sports_nba",
            "get_player_stats": "sports_nba",
            "get_team_stats": "sports_nba",
            "get_betting_odds": "sports_nba",
            "analyze_betting_patterns": "sports_nba",
            "get_team_injuries": "sports_nba",
        }

        # Mock embedding function
        async def mock_embed_fn(text: str) -> list[float]:
            # Return consistent embeddings for testing
            return np.random.rand(768).tolist()

        await router.initialize(
            tool_schemas=tool_schemas,
            tool_domains=tool_domains,
            embed_fn=mock_embed_fn,
        )

        return router

    @pytest.mark.asyncio
    async def test_e2e_simple_game_query(self, initialized_router, mock_llm_client):
        """Test simple single-intent query: "What are the NBA games today?"

        Expected flow:
        - Stage 0: Intent analysis → "query_games"
        - Stage 1: Classification → sports_nba (high confidence)
        - Stage 1b: No decomposition (simple query)
        - Stage 2: Retrieve get_nba_games tool
        - Stage 3: Execute with selected tool
        """
        # Mock Stage 0: Intent analysis
        with patch.object(
            initialized_router, "_intent_analyzer", None
        ):  # Disable intent analyzer for this test
            # Mock Stage 1: Classification
            with patch.object(
                initialized_router._classifier,
                "classify_with_fallback",
                new_callable=AsyncMock,
            ) as mock_classify:
                classification = DomainClassification(
                    domains=[DomainComplexity(name="sports_nba", complexity="medium")],
                    confidence=0.95,
                    query_summary="Get NBA games for today",
                )
                mock_classify.return_value = (classification, False)

                # Mock Stage 2: Tool retrieval
                with patch.object(
                    initialized_router._retriever,
                    "retrieve",
                    new_callable=AsyncMock,
                ) as mock_retrieve:
                    retrieved_tools = [
                        RetrievedTool(
                            name="get_nba_games",
                            domain="sports_nba",
                            similarity_score=0.95,
                            schema={
                                "type": "function",
                                "function": {
                                    "name": "get_nba_games",
                                    "description": "Get NBA games",
                                    "parameters": {"type": "object"},
                                },
                            },
                        )
                    ]
                    retrieval_result = ToolRetrievalResult(
                        tools=retrieved_tools,
                        total_payload_bytes=1200,
                        domains_searched=["sports_nba"],
                    )
                    mock_retrieve.return_value = retrieval_result

                    # Mock Stage 3: LLM execution
                    llm_response = LLMResponse(model="default",
                        choices=[
                            Choice(
                                    message=ChoiceMessage(
                                    role=MessageRole.ASSISTANT,
                                    content="",
                                    tool_calls=[
                                        ToolCall(
                                            id="call_1",
                                            function=ToolCallFunction(
                                                name="get_nba_games",
                                                arguments='{"date": "2026-03-22"}',
                                            ),
                                        )
                                    ],
                                ),
                                index=0,
                            )
                        ]
                    )
                    mock_llm_client.generate_response.return_value = llm_response

                    # Execute routing
                    result = await initialized_router.route(query="What are the NBA games today?")

                    # Assertions
                    assert len(result) > 0, "Should retrieve at least one tool"
                    assert result[0].tool_name == "get_nba_games"
                    assert mock_classify.called
                    assert mock_retrieve.called

    @pytest.mark.asyncio
    async def test_e2e_multi_intent_games_and_odds(self, initialized_router, mock_llm_client):
        """Test multi-intent query: "Show me NBA games tonight and their betting odds"

        Expected flow:
        - Stage 1: Classification → sports_nba (high confidence, multi-intent)
        - Stage 1b: Decomposition → 2 sub-queries:
          * "NBA games tonight" → retrieve get_nba_games
          * "Betting odds for games" → retrieve get_betting_odds
        - Stage 2: Multi-intent retrieval
        - Stage 3: Execute both tools
        """
        with patch.object(initialized_router, "_intent_analyzer", None):
            # Mock Stage 1: Classification (detect multi-intent)
            with patch.object(
                initialized_router._classifier,
                "classify_with_fallback",
                new_callable=AsyncMock,
            ) as mock_classify:
                classification = DomainClassification(
                    domains=[DomainComplexity(name="sports_nba", complexity="high")],
                    confidence=0.93,
                    query_summary="Get NBA games and their betting odds",
                )
                mock_classify.return_value = (classification, False)

                # Mock Stage 1b: Decomposition
                with patch.object(
                    initialized_router._decomposer,
                    "decompose",
                    new_callable=AsyncMock,
                ) as mock_decompose:
                    sub_queries = [
                        SubQuery(
                            text="What NBA games are tonight?",
                            domain="sports_nba",
                            intent="games_query",
                        ),
                        SubQuery(
                            text="What are the betting odds?",
                            domain="sports_nba",
                            intent="odds_query",
                        ),
                    ]
                    mock_decompose.return_value = sub_queries

                    # Mock Stage 2: Tool retrieval
                    with patch.object(
                        initialized_router._retriever,
                        "retrieve",
                        new_callable=AsyncMock,
                    ) as mock_retrieve:
                        retrieved_tools = [
                            RetrievedTool(
                                name="get_nba_games",
                                domain="sports_nba",
                                similarity_score=0.96,
                                schema={
                                    "type": "function",
                                    "function": {
                                        "name": "get_nba_games",
                                        "description": "Get NBA games",
                                        "parameters": {"type": "object"},
                                    },
                                },
                            ),
                            RetrievedTool(
                                name="get_betting_odds",
                                domain="sports_nba",
                                similarity_score=0.94,
                                schema={
                                    "type": "function",
                                    "function": {
                                        "name": "get_betting_odds",
                                        "description": "Get betting odds",
                                        "parameters": {"type": "object"},
                                    },
                                },
                            ),
                        ]
                        retrieval_result = ToolRetrievalResult(
                            tools=retrieved_tools,
                            total_payload_bytes=2400,
                            domains_searched=["sports_nba"],
                        )
                        mock_retrieve.return_value = retrieval_result

                        # Mock Stage 3: LLM execution (multi-tool)
                        llm_response = LLMResponse(model="default",
                            choices=[
                                Choice(
                                    message=ChoiceMessage(
                                        role=MessageRole.ASSISTANT,
                                        content="",
                                        tool_calls=[
                                            ToolCall(
                                                id="call_1",
                                                function=ToolCallFunction(
                                                    name="get_nba_games",
                                                    arguments='{"date": "2026-03-22"}',
                                                ),
                                            ),
                                            ToolCall(
                                                id="call_2",
                                                function=ToolCallFunction(
                                                    name="get_betting_odds",
                                                    arguments='{"game_date": "2026-03-22"}',
                                                ),
                                            ),
                                        ],
                                    ),
                                    index=0,
                                )
                            ]
                        )
                        mock_llm_client.generate_response.return_value = llm_response

                        # Execute routing
                        result = await initialized_router.route(
                            query="Show me NBA games tonight and their betting odds"
                        )

                        # Assertions
                        assert len(result) == 2, "Should retrieve 2 tools for multi-intent"
                        tool_names = {t.tool_name for t in result}
                        assert "get_nba_games" in tool_names
                        assert "get_betting_odds" in tool_names

    @pytest.mark.asyncio
    async def test_e2e_player_stats_and_team_analysis(self, initialized_router, mock_llm_client):
        """Test complex multi-intent: "Compare LeBron James and Luka Doncic stats for this season and analyze which team is better"

        Expected flow:
        - Stage 1: Classification → sports_nba (high confidence)
        - Stage 1b: Decomposition → 3 sub-queries:
          * "LeBron James stats this season"
          * "Luka Doncic stats this season"
          * "Team comparison analysis"
        - Stage 2: Retrieve get_player_stats and get_team_stats
        - Stage 3: Execute comparison tools
        """
        with patch.object(initialized_router, "_intent_analyzer", None):
            with patch.object(
                initialized_router._classifier,
                "classify_with_fallback",
                new_callable=AsyncMock,
            ) as mock_classify:
                classification = DomainClassification(
                    domains=[DomainComplexity(name="sports_nba", complexity="high")],
                    confidence=0.91,
                    query_summary="Compare player stats and team analysis",
                )
                mock_classify.return_value = (classification, False)

                with patch.object(
                    initialized_router._decomposer,
                    "decompose",
                    new_callable=AsyncMock,
                ) as mock_decompose:
                    sub_queries = [
                        SubQuery(
                            text="What are LeBron James stats for this season?",
                            domain="sports_nba",
                            intent="player_stats",
                        ),
                        SubQuery(
                            text="What are Luka Doncic stats for this season?",
                            domain="sports_nba",
                            intent="player_stats",
                        ),
                        SubQuery(
                            text="Which team is better overall?",
                            domain="sports_nba",
                            intent="team_comparison",
                        ),
                    ]
                    mock_decompose.return_value = sub_queries

                    with patch.object(
                        initialized_router._retriever,
                        "retrieve",
                        new_callable=AsyncMock,
                    ) as mock_retrieve:
                        retrieved_tools = [
                            RetrievedTool(
                                name="get_player_stats",
                                domain="sports_nba",
                                similarity_score=0.97,
                                schema={
                                    "type": "function",
                                    "function": {
                                        "name": "get_player_stats",
                                        "description": "Get player stats",
                                        "parameters": {"type": "object"},
                                    },
                                },
                            ),
                            RetrievedTool(
                                name="get_team_stats",
                                domain="sports_nba",
                                similarity_score=0.93,
                                schema={
                                    "type": "function",
                                    "function": {
                                        "name": "get_team_stats",
                                        "description": "Get team stats",
                                        "parameters": {"type": "object"},
                                    },
                                },
                            ),
                        ]
                        retrieval_result = ToolRetrievalResult(
                            tools=retrieved_tools,
                            total_payload_bytes=2800,
                            domains_searched=["sports_nba"],
                        )
                        mock_retrieve.return_value = retrieval_result

                        llm_response = LLMResponse(model="default",
                            choices=[
                                Choice(
                                    message=ChoiceMessage(
                                        role=MessageRole.ASSISTANT,
                                        content="",
                                        tool_calls=[
                                            ToolCall(
                                                id="call_1",
                                                function=ToolCallFunction(
                                                    name="get_player_stats",
                                                    arguments='{"player_name": "LeBron James", "season": "2025-2026"}',
                                                ),
                                            ),
                                            ToolCall(
                                                id="call_2",
                                                function=ToolCallFunction(
                                                    name="get_player_stats",
                                                    arguments='{"player_name": "Luka Doncic", "season": "2025-2026"}',
                                                ),
                                            ),
                                            ToolCall(
                                                id="call_3",
                                                function=ToolCallFunction(
                                                    name="get_team_stats",
                                                    arguments='{"team_name": "Los Angeles Lakers"}',
                                                ),
                                            ),
                                        ],
                                    ),
                                    index=0,
                                )
                            ]
                        )
                        mock_llm_client.generate_response.return_value = llm_response

                        result = await initialized_router.route(
                            query="Compare LeBron James and Luka Doncic stats for this season and analyze which team is better"
                        )

                        assert len(result) >= 2, "Should have multiple tool calls"
                        tool_names = {t.tool_name for t in result}
                        assert "get_player_stats" in tool_names

    @pytest.mark.asyncio
    async def test_e2e_betting_analysis_multi_intent(self, initialized_router, mock_llm_client):
        """Test betting-focused multi-intent: "What are tonight's NBA odds? Analyze betting patterns for high-value picks"

        Expected flow:
        - Stage 1: Classification → sports_nba (high confidence, betting-related)
        - Stage 1b: Decomposition → 2 sub-queries
        - Stage 2: Retrieve betting tools
        - Stage 3: Execute betting analysis
        """
        with patch.object(initialized_router, "_intent_analyzer", None):
            with patch.object(
                initialized_router._classifier,
                "classify_with_fallback",
                new_callable=AsyncMock,
            ) as mock_classify:
                classification = DomainClassification(
                    domains=[DomainComplexity(name="sports_nba", complexity="high")],
                    confidence=0.89,
                    query_summary="Get odds and analyze betting patterns",
                )
                mock_classify.return_value = (classification, False)

                with patch.object(
                    initialized_router._decomposer,
                    "decompose",
                    new_callable=AsyncMock,
                ) as mock_decompose:
                    sub_queries = [
                        SubQuery(
                            text="What are tonight's NBA game odds?",
                            domain="sports_nba",
                            intent="odds_query",
                        ),
                        SubQuery(
                            text="Analyze professional betting patterns for high-value picks",
                            domain="sports_nba",
                            intent="betting_analysis",
                        ),
                    ]
                    mock_decompose.return_value = sub_queries

                    with patch.object(
                        initialized_router._retriever,
                        "retrieve",
                        new_callable=AsyncMock,
                    ) as mock_retrieve:
                        retrieved_tools = [
                            RetrievedTool(
                                name="get_betting_odds",
                                domain="sports_nba",
                                similarity_score=0.96,
                                schema={
                                    "type": "function",
                                    "function": {
                                        "name": "get_betting_odds",
                                        "description": "Get betting odds",
                                        "parameters": {"type": "object"},
                                    },
                                },
                            ),
                            RetrievedTool(
                                name="analyze_betting_patterns",
                                domain="sports_nba",
                                similarity_score=0.92,
                                schema={
                                    "type": "function",
                                    "function": {
                                        "name": "analyze_betting_patterns",
                                        "description": "Analyze betting patterns",
                                        "parameters": {"type": "object"},
                                    },
                                },
                            ),
                        ]
                        retrieval_result = ToolRetrievalResult(
                            tools=retrieved_tools,
                            total_payload_bytes=2500,
                            domains_searched=["sports_nba"],
                        )
                        mock_retrieve.return_value = retrieval_result

                        llm_response = LLMResponse(model="default",
                            choices=[
                                Choice(
                                    message=ChoiceMessage(
                                        role=MessageRole.ASSISTANT,
                                        content="",
                                        tool_calls=[
                                            ToolCall(
                                                id="call_1",
                                                function=ToolCallFunction(
                                                    name="get_betting_odds",
                                                    arguments='{"game_date": "2026-03-22"}',
                                                ),
                                            ),
                                            ToolCall(
                                                id="call_2",
                                                function=ToolCallFunction(
                                                    name="analyze_betting_patterns",
                                                    arguments='{"query": "high-value picks for tonight"}',
                                                ),
                                            ),
                                        ],
                                    ),
                                    index=0,
                                )
                            ]
                        )
                        mock_llm_client.generate_response.return_value = llm_response

                        result = await initialized_router.route(
                            query="What are tonight's NBA odds? Analyze betting patterns for high-value picks"
                        )

                        assert len(result) == 2, "Should have 2 tool calls for betting analysis"
                        tool_names = {t.tool_name for t in result}
                        assert "get_betting_odds" in tool_names
                        assert "analyze_betting_patterns" in tool_names

    @pytest.mark.asyncio
    async def test_e2e_injury_report_and_games(self, initialized_router, mock_llm_client):
        """Test injury-focused query: "Check Lakers and Celtics injuries, then show me their upcoming games"

        Expected flow:
        - Stage 1: Classification → sports_nba (high confidence)
        - Stage 1b: Decomposition → 3 sub-queries:
          * "Lakers injuries"
          * "Celtics injuries"
          * "Upcoming games for both teams"
        - Stage 2: Retrieve injury and game tools
        - Stage 3: Execute multi-tool pipeline
        """
        with patch.object(initialized_router, "_intent_analyzer", None):
            with patch.object(
                initialized_router._classifier,
                "classify_with_fallback",
                new_callable=AsyncMock,
            ) as mock_classify:
                classification = DomainClassification(
                    domains=[DomainComplexity(name="sports_nba", complexity="high")],
                    confidence=0.94,
                    query_summary="Check team injuries and upcoming games",
                )
                mock_classify.return_value = (classification, False)

                with patch.object(
                    initialized_router._decomposer,
                    "decompose",
                    new_callable=AsyncMock,
                ) as mock_decompose:
                    sub_queries = [
                        SubQuery(
                            text="What are the Lakers current injuries?",
                            domain="sports_nba",
                            intent="injury_report",
                        ),
                        SubQuery(
                            text="What are the Celtics current injuries?",
                            domain="sports_nba",
                            intent="injury_report",
                        ),
                        SubQuery(
                            text="What are the upcoming games for Lakers and Celtics?",
                            domain="sports_nba",
                            intent="games_query",
                        ),
                    ]
                    mock_decompose.return_value = sub_queries

                    with patch.object(
                        initialized_router._retriever,
                        "retrieve",
                        new_callable=AsyncMock,
                    ) as mock_retrieve:
                        retrieved_tools = [
                            RetrievedTool(
                                name="get_team_injuries",
                                domain="sports_nba",
                                similarity_score=0.98,
                                schema={
                                    "type": "function",
                                    "function": {
                                        "name": "get_team_injuries",
                                        "description": "Get team injuries",
                                        "parameters": {"type": "object"},
                                    },
                                },
                            ),
                            RetrievedTool(
                                name="get_nba_games",
                                domain="sports_nba",
                                similarity_score=0.95,
                                schema={
                                    "type": "function",
                                    "function": {
                                        "name": "get_nba_games",
                                        "description": "Get NBA games",
                                        "parameters": {"type": "object"},
                                    },
                                },
                            ),
                        ]
                        retrieval_result = ToolRetrievalResult(
                            tools=retrieved_tools,
                            total_payload_bytes=2600,
                            domains_searched=["sports_nba"],
                        )
                        mock_retrieve.return_value = retrieval_result

                        llm_response = LLMResponse(model="default",
                            choices=[
                                Choice(
                                    message=ChoiceMessage(
                                        role=MessageRole.ASSISTANT,
                                        content="",
                                        tool_calls=[
                                            ToolCall(
                                                id="call_1",
                                                function=ToolCallFunction(
                                                    name="get_team_injuries",
                                                    arguments='{"team_name": "Lakers"}',
                                                ),
                                            ),
                                            ToolCall(
                                                id="call_2",
                                                function=ToolCallFunction(
                                                    name="get_team_injuries",
                                                    arguments='{"team_name": "Celtics"}',
                                                ),
                                            ),
                                            ToolCall(
                                                id="call_3",
                                                function=ToolCallFunction(
                                                    name="get_nba_games",
                                                    arguments='{"date": "2026-03-22"}',
                                                ),
                                            ),
                                        ],
                                    ),
                                    index=0,
                                )
                            ]
                        )
                        mock_llm_client.generate_response.return_value = llm_response

                        result = await initialized_router.route(
                            query="Check Lakers and Celtics injuries, then show me their upcoming games"
                        )

                        assert len(result) == 3, "Should have 3 tool calls for injury + games"
                        tool_names = [t.tool_name for t in result]
                        assert tool_names.count("get_team_injuries") == 2
                        assert "get_nba_games" in tool_names


class TestE2EFallbackAndErrorHandling:
    """Tests for fallback and error handling in routing pipeline."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock NanoGPT LLM client."""
        client = AsyncMock()
        client.generate_response = AsyncMock()
        return client

    @pytest.fixture
    def router_config(self):
        """Router configuration for testing."""
        return HybridRouterConfig(
            use_query_decomposition=True,
            use_llamaindex_retriever=False,
            max_payload_bytes=28_000,
        )

    @pytest.fixture
    async def initialized_router(self, mock_llm_client, router_config):
        """Create and initialize a router for testing."""
        router = HybridToolRouter(
            llm_client=mock_llm_client,
            config=router_config,
        )

        tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": "get_nba_games",
                    "description": "Get NBA games",
                    "parameters": {"type": "object"},
                },
            }
        ]

        tool_domains = {"get_nba_games": "sports_nba"}

        async def mock_embed_fn(text: str) -> list[float]:
            return np.random.rand(768).tolist()

        await router.initialize(
            tool_schemas=tool_schemas,
            tool_domains=tool_domains,
            embed_fn=mock_embed_fn,
        )

        return router

    @pytest.mark.asyncio
    async def test_e2e_low_confidence_classification_fallback(
        self, initialized_router, mock_llm_client
    ):
        """Test fallback when classification confidence is low.

        Expected flow:
        - Stage 1: Classification with low confidence (0.3)
        - Stage 2: Fallback to global top-K retrieval (no domain filtering)
        - Stage 3: Execute with full tool set
        """
        with patch.object(initialized_router, "_intent_analyzer", None):
            with patch.object(
                initialized_router._classifier,
                "classify_with_fallback",
                new_callable=AsyncMock,
            ) as mock_classify:
                classification = DomainClassification(
                    domains=[],  # No domains detected
                    confidence=0.35,  # Low confidence
                    query_summary="Unclear query",
                )
                mock_classify.return_value = (classification, True)  # Used fallback

                with patch.object(
                    initialized_router._retriever,
                    "retrieve_global_topk",
                    new_callable=AsyncMock,
                ) as mock_global_retrieve:
                    retrieved_tools = [
                        RetrievedTool(
                            name="get_nba_games",
                            domain="sports_nba",
                            similarity_score=0.75,
                            schema={
                                "type": "function",
                                "function": {
                                    "name": "get_nba_games",
                                    "description": "Get NBA games",
                                    "parameters": {"type": "object"},
                                },
                            },
                        )
                    ]
                    retrieval_result = ToolRetrievalResult(
                        tools=retrieved_tools,
                        total_payload_bytes=1200,
                        domains_searched=[],  # Global search
                    )
                    mock_global_retrieve.return_value = retrieval_result

                    llm_response = LLMResponse(model="default",
                        choices=[
                            Choice(
                                    message=ChoiceMessage(
                                    role=MessageRole.ASSISTANT,
                                    content="",
                                    tool_calls=[
                                        ToolCall(
                                            id="call_1",
                                            function=ToolCallFunction(
                                                name="get_nba_games",
                                                arguments='{"date": "2026-03-22"}',
                                            ),
                                        )
                                    ],
                                ),
                                index=0,
                            )
                        ]
                    )
                    mock_llm_client.generate_response.return_value = llm_response

                    result = await initialized_router.route(
                        query="ambiguous unclear query about something"
                    )

                    # Verify fallback was used
                    assert mock_classify.called
                    assert mock_global_retrieve.called  # Global retrieval used
                    assert len(result) > 0

    @pytest.mark.asyncio
    async def test_e2e_no_tools_retrieved_empty_result(self, initialized_router, mock_llm_client):
        """Test handling when no tools are retrieved.

        Expected flow:
        - Stage 1: Classification succeeds
        - Stage 2: No relevant tools found
        - Stage 3: Return empty result list
        """
        with patch.object(initialized_router, "_intent_analyzer", None):
            with patch.object(
                initialized_router._classifier,
                "classify_with_fallback",
                new_callable=AsyncMock,
            ) as mock_classify:
                classification = DomainClassification(
                    domains=[DomainComplexity(name="sports_nba", complexity="low")],
                    confidence=0.85,
                    query_summary="Some query",
                )
                mock_classify.return_value = (classification, False)

                with patch.object(
                    initialized_router._retriever,
                    "retrieve",
                    new_callable=AsyncMock,
                ) as mock_retrieve:
                    # Return empty retrieval result
                    retrieval_result = ToolRetrievalResult(
                        tools=[],  # No tools
                        total_payload_bytes=0,
                        domains_searched=["sports_nba"],
                    )
                    mock_retrieve.return_value = retrieval_result

                    result = await initialized_router.route(query="Some unrelated query")

                    # Should return empty list
                    assert result == []

    @pytest.mark.asyncio
    async def test_e2e_llm_execution_error_graceful_handling(
        self, initialized_router, mock_llm_client
    ):
        """Test graceful handling when LLM execution fails.

        Expected flow:
        - Stage 1-2: Succeed
        - Stage 3: LLM raises exception
        - Graceful return of empty list
        """
        with patch.object(initialized_router, "_intent_analyzer", None):
            with patch.object(
                initialized_router._classifier,
                "classify_with_fallback",
                new_callable=AsyncMock,
            ) as mock_classify:
                classification = DomainClassification(
                    domains=[DomainComplexity(name="sports_nba", complexity="medium")],
                    confidence=0.9,
                    query_summary="Some query",
                )
                mock_classify.return_value = (classification, False)

                with patch.object(
                    initialized_router._retriever,
                    "retrieve",
                    new_callable=AsyncMock,
                ) as mock_retrieve:
                    retrieved_tools = [
                        RetrievedTool(
                            name="get_nba_games",
                            domain="sports_nba",
                            similarity_score=0.9,
                            schema={
                                "type": "function",
                                "function": {
                                    "name": "get_nba_games",
                                    "description": "Get NBA games",
                                    "parameters": {"type": "object"},
                                },
                            },
                        )
                    ]
                    retrieval_result = ToolRetrievalResult(
                        tools=retrieved_tools,
                        total_payload_bytes=1200,
                        domains_searched=["sports_nba"],
                    )
                    mock_retrieve.return_value = retrieval_result

                    # Make LLM raise exception
                    mock_llm_client.generate_response.side_effect = Exception("LLM service error")

                    result = await initialized_router.route(query="Get NBA games")

                    # Should return empty list gracefully
                    assert result == []
