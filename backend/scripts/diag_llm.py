import asyncio
import os
from me4brain.llm import get_llm_client, LLMRequest, Message
from me4brain.retrieval.prompts import ENTITY_EXTRACTION_PROMPT


async def test_mistral_extraction():
    client = get_llm_client()
    text = "Arduino Uno è una scheda elettronica basata sul microcontrollore ATmega328P."
    prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)

    # Test SENZA json_object
    request = LLMRequest(
        model="mistralai/mistral-large-3-675b-instruct-2512",
        messages=[Message(role="user", content=prompt)],
        temperature=0.1,
        # response_format rimosso
    )
    print(f"Testing extraction with Mistral Large 3 (NO JSON MODE)...")
    try:
        response = await client.generate_response(request)
        print(f"SUCCESS: {response.choices[0].message.content[:200]}...")
    except Exception as e:
        print(f"FAILED: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_mistral_extraction())
