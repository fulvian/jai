"""Standalone verification for Ollama Integration."""

import asyncio
import json
from unittest.mock import MagicMock, patch

# Mock dependencies that might be missing in standalone mode
import sys
from types import ModuleType


def mock_module(name):
    m = ModuleType(name)
    sys.modules[name] = m
    return m


# Mock structlog if needed
if "structlog" not in sys.modules:
    sl = mock_module("structlog")
    sl.get_logger = lambda x: MagicMock()


async def verify():
    print("--- Verificando Ollama Integration ---")

    from me4brain.llm.ollama import OllamaClient
    from me4brain.llm.config import LLMConfig
    from me4brain.llm.models import LLMRequest, Message
    from me4brain.llm.provider_factory import get_tool_calling_client

    # 1. Test Config
    config = LLMConfig()
    config.use_local_tool_calling = True
    config.ollama_model = "lfm2.5-thinking:latest"
    print(f"Config: use_local={config.use_local_tool_calling}, model={config.ollama_model}")

    # 2. Test Client Instantiation
    client = OllamaClient(base_url="http://localhost:11434/v1")
    print("OllamaClient istanziato correttamente.")

    # 3. Test Provider Factory Dispatch
    with patch("me4brain.llm.provider_factory.get_llm_config", return_value=config):
        tc_client = get_tool_calling_client()
        print(f"Provider Factory returned: {type(tc_client).__name__}")
        if isinstance(tc_client, OllamaClient):
            print("SUCCESS: Factory ha restituito OllamaClient per agentic task.")
        else:
            print("FAILURE: Factory non ha restituito OllamaClient.")

    # 4. Test Native Tool Selection logic (Mocking HTTP)
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self.json_data = json_data
            self.text = json.dumps(json_data)

        def json(self):
            return self.json_data

    class MockAsyncClient:
        async def post(self, url, **kwargs):
            return MockResponse(
                200,
                {"choices": [{"message": {"content": "Tool call simulated", "tool_calls": []}}]},
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    with patch("httpx.AsyncClient", return_value=MockAsyncClient()):
        request = LLMRequest(model="test", messages=[Message(role="user", content="test")])
        response = await client.generate_response(request)
        print(f"Simulated response content: {response.content}")
        if response.content == "Tool call simulated":
            print("SUCCESS: OllamaClient ha gestito correttamente la richiesta simulata.")

    print("--- Verifica Completata ---")


if __name__ == "__main__":
    asyncio.run(verify())
