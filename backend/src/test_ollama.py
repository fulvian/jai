import asyncio
from me4brain.llm.models import LLMRequest, Message, MessageRole
from me4brain.llm.ollama import get_ollama_client

async def test():
    client = get_ollama_client()
    req = LLMRequest(
        model="/Users/fulvio/.lmstudio/models/mlx-community/Qwen3.5-4B-MLX-4bit",
        messages=[Message(role=MessageRole.USER, content="Ciao")],
        stream=True
    )
    async for chunk in client.stream_response(req):
        print(chunk.content)

asyncio.run(test())
