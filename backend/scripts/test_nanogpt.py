"""Test script per verificare l'integrazione con NanoGPT.

Esegue test su modelli configurati, inclusa analisi di file locali (Vision/Document).
"""

import asyncio
import base64
import mimetypes
import os
import sys
from pathlib import Path

# Aggiunge src al path per importare i moduli
sys.path.append(str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from me4brain.llm import (
    LLMRequest,
    Message,
    MessageContent,
    NanoGPTClient,
    ReasoningLevel,
    get_llm_config,
)
from me4brain.utils.logging import configure_logging

# Carica .env
load_dotenv()
configure_logging()


def encode_image(image_path: str) -> str:
    """Codifica un file in base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


async def analyze_local_file(client: NanoGPTClient, model: str, file_path: Path):
    """Analizza un file locale inviandolo come data URI."""
    print(f"\n📂 Analyzing file: {file_path.name}")

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        # Fallback per estensioni note se mimetypes fallisce
        if file_path.suffix.lower() == ".bmp":
            mime_type = "image/bmp"
        else:
            mime_type = "application/octet-stream"

    print(f"   Type: {mime_type}")

    base64_image = encode_image(str(file_path))
    data_url = f"data:{mime_type};base64,{base64_image}"

    request = LLMRequest(
        model=model,
        messages=[
            Message(
                role="user",
                content=[
                    MessageContent(
                        type="text",
                        text="Please analyze this file/image deeply. Describe what you see, identify any key information, medical details if applicable, or document structure.",
                    ),
                    MessageContent(type="image_url", image_url={"url": data_url}),
                ],
            )
        ],
        max_tokens=800,
    )

    try:
        print("   ⏳ Sending request...")
        response = await client.generate_response(request)
        print(f"   ✅ Response received ({response.latency_ms}ms):")
        if response.reasoning:
            print(f"   🧠 Reasoning: {response.reasoning[:200]}...")
        print(f"   📝 Content: {response.content}\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")


async def main():
    print("🚀 Inizio test NanoGPT Client (Local Files)...")
    config = get_llm_config()

    if not config.nanogpt_api_key or config.nanogpt_api_key == "your_nanogpt_api_key_here":
        print("❌ ERRORE: NANOGPT_API_KEY non impostata in .env")
        return

    client = NanoGPTClient(api_key=config.nanogpt_api_key, base_url=config.nanogpt_base_url)

    # Directory esempi
    examples_dir = Path(__file__).parent.parent / "examples"
    if not examples_dir.exists():
        print(f"❌ Directory examples non trovata: {examples_dir}")
        return

    # Files to test
    files = [f for f in examples_dir.iterdir() if f.is_file() and f.name != ".DS_Store"]

    if not files:
        print("❌ Nessun file trovato in examples/")
        return

    print(f"Found {len(files)} files to analyze using model {config.model_vision} (Kimi K2.5)")

    for file_path in files:
        await analyze_local_file(client, config.model_vision, file_path)

    print("\n🎉 Test completati.")


if __name__ == "__main__":
    asyncio.run(main())
