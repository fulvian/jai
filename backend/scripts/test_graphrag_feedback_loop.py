import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from me4brain.engine.iterative_executor import IterativeExecutor
from me4brain.engine.hybrid_router.types import SubQuery, RetrievedTool
from me4brain.llm.models import LLMResponse, ToolCall, ToolCallFunction


class TestGraphRAGFeedbackLoop(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_llm = MagicMock()
        self.mock_registry = MagicMock()
        self.executor = IterativeExecutor(
            llm_client=self.mock_llm,
            retriever=MagicMock(),
            executor=MagicMock(),
            model="test-model",
        )

    @patch("me4brain.engine.iterative_executor.IterativeExecutor._get_graph_prompt_hints")
    async def test_validation_feedback_loop(self, mock_get_hints):
        # 1. Setup GraphRAG Layer 3 Constraints for a test tool
        mock_get_hints.return_value = {
            "hints": "STRICT RULES: 'city' parameter is mandatory and must be a string.",
            "constraints": {
                "get_weather": {
                    "input_schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    }
                }
            },
        }

        # 2. Setup LLM to fail first, then succeed
        # Attempt 1: Hallucinates 'location' instead of 'city'
        resp1 = MagicMock(spec=LLMResponse)
        func1 = MagicMock()
        func1.name = "get_weather"
        func1.arguments = json.dumps({"location": "Rome"})
        resp1.tool_calls = [MagicMock(function=func1)]

        # Attempt 2: Corrects to 'city'
        resp2 = MagicMock(spec=LLMResponse)
        func2 = MagicMock()
        func2.name = "get_weather"
        func2.arguments = json.dumps({"city": "Rome"})
        resp2.tool_calls = [MagicMock(function=func2)]

        self.mock_llm.generate_response = AsyncMock(side_effect=[resp1, resp2])

        # 3. Execute _select_tools_for_step
        sub_query = SubQuery(text="Che tempo fa a Roma?", domain="weather_geo")
        tools = [
            RetrievedTool(
                name="get_weather",
                domain="weather_geo",
                similarity_score=0.99,
                schema={
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather",
                        "parameters": {},
                    },
                },
            )
        ]

        results = await self.executor._select_tools_for_step(
            step_id=1, sub_query=sub_query, tools=tools, previous_context="", extra_context=None
        )

        # 4. Assertions
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "get_weather")
        self.assertEqual(results[0].arguments["city"], "Rome")

        # Verify LLM was called twice (initial + feedback loop)
        self.assertEqual(self.mock_llm.generate_response.call_count, 2)

        # Verify the second call included the feedback
        second_call_args = self.mock_llm.generate_response.call_args_list[1][0][0]
        user_msg = str(
            getattr(second_call_args.messages[1], "content", second_call_args.messages[1])
        )
        self.assertIn("ERRORE VALIDAZIONE PRECEDENTE", user_msg)
        self.assertIn("parametro mancante: 'city'", user_msg)


if __name__ == "__main__":
    unittest.main()
