import asyncio

import httpx


async def test():
    client = httpx.AsyncClient(base_url="http://localhost:1234/v1/")
    payload = {
        "model": "/Users/fulvio/.lmstudio/models/mlx-community/Qwen3.5-4B-MLX-4bit",
        "messages": [{"role": "user", "content": "Ciao"}],
    }
    try:
        r = await client.post("chat/completions", json=payload)
        print("STATUS:", r.status_code)
        print("BODY:", r.text)
    except Exception as e:
        print("ERROR:", e)


asyncio.run(test())
