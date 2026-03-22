import asyncio
from me4brain.llm import get_llm_client, LLMRequest, Message


async def test_json_mode():
    client = get_llm_client()
    request = LLMRequest(
        model="mistralai/mistral-large-3-675b-instruct-2512",
        messages=[Message(role="user", content='Restituisci questo JSON: {"status": "ok"}')],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    print(f"Testing Mistral Large 3 WITH JSON MODE...")
    try:
        response = await client.generate_response(request)
        print(f"SUCCESS: {response.choices[0].message.content}")
    except Exception as e:
        print(f"FAILED: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_json_mode())
