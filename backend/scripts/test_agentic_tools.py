"""Test script per verificare le capacità Agentic (Tool Calling) dei modelli GLM 4.7.

Esegue test chiamando il modello Agentic configurato e verificando se genera tool calls corrette.
"""

import asyncio
import json
import sys
from pathlib import Path

# Aggiunge src al path per importare i moduli
sys.path.append(str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from me4brain.llm import (
    LLMRequest,
    Message,
    NanoGPTClient,
    Tool,
    ToolFunction,
    get_llm_config,
)
from me4brain.utils.logging import configure_logging

# Carica .env
load_dotenv()
configure_logging()


async def main():
    print("🚀 Inizio test Agentic Tools (GLM 4.7)...")

    config = get_llm_config()
    print(f"🤖 Agentic Model: {config.model_agentic}")
    print(f"⚡ Fast Agentic Model: {config.model_agentic_fast}")

    if not config.nanogpt_api_key or config.nanogpt_api_key == "your_nanogpt_api_key_here":
        print("❌ ERRORE: NANOGPT_API_KEY non impostata in .env")
        return

    client = NanoGPTClient(api_key=config.nanogpt_api_key, base_url=config.nanogpt_base_url)

    # Definizione Tool Dummy (Meteo)
    weather_tool = Tool(
        type="function",
        function=ToolFunction(
            name="get_current_weather",
            description="Get the current weather in a given location",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit",
                    },
                },
                "required": ["location"],
            },
        ),
    )

    # Test 1: Tool Call Generativa (Thinking Model)
    # GLM 4.7 Thinking dovrebbe prima ragionare e poi chiamare il tool
    print(f"\n🧪 Test 1: Tool Call with Reasoning (Model: {config.model_agentic})")
    request = LLMRequest(
        model=config.model_agentic,
        messages=[
            Message(
                role="user",
                content="What is the weather like in Florence, Italy today? I need to know if I should bring an umbrella.",
            )
        ],
        tools=[weather_tool],
        tool_choice="auto",
        temperature=0.1,  # Bassa temperatura per determinismo nei tool
    )

    try:
        response = await client.generate_response(request)
        print(f"✅ Response received ({response.latency_ms}ms):")

        if response.reasoning:
            print(f"🧠 Reasoning: {response.reasoning[:200]}...")

        if response.tool_calls:
            print(f"🛠️ Tool Calls: {len(response.tool_calls)}")
            for tc in response.tool_calls:
                print(f"   Function: {tc.function.name}")
                print(f"   Args: {tc.function.arguments}")

                # Verify JSON args
                try:
                    args = json.loads(tc.function.arguments)
                    print(f"   Parsed Args: {args}")
                except json.JSONDecodeError:
                    print("   ❌ Invalid JSON arguments")
        else:
            print(f"📝 Content (No Tool Call): {response.content}")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 2: Fast Tool Call (Fast Model)
    # GLM 4.7 Fast dovrebbe essere diretto
    print(f"\n🧪 Test 2: Fast Tool Call (Model: {config.model_agentic_fast})")
    request_fast = LLMRequest(
        model=config.model_agentic_fast,
        messages=[Message(role="user", content="Get weather for Rome.")],
        tools=[weather_tool],
        tool_choice="auto",
    )

    try:
        response_fast = await client.generate_response(request_fast)
        print(f"✅ Response received ({response_fast.latency_ms}ms):")

        if response_fast.tool_calls:
            print(f"🛠️ Tool Calls: {len(response_fast.tool_calls)}")
            for tc in response_fast.tool_calls:
                print(f"   Function: {tc.function.name}")
                print(f"   Args: {tc.function.arguments}")
        else:
            print(f"📝 Content (No Tool Call): {response_fast.content}")

    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n🎉 Test Agentic completati.")


if __name__ == "__main__":
    asyncio.run(main())
