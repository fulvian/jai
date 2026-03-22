"""Test script per il servizio OCR Ibrido.

Verifica che:
1. File PDF nativi vengano processati localmente (pypdf).
2. File immagini (o PDF scansionati) vengano processati via Vision AI (Kimi K2.5).
"""

import asyncio
import sys
from pathlib import Path

# Aggiunge src al path per importare i moduli
sys.path.append(str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from me4brain.ingestion.ocr import HybridOCRService
from me4brain.utils.logging import configure_logging

# Carica .env
load_dotenv()
configure_logging()


async def main():
    print("🚀 Inizio test Hybrid OCR Service...")

    ocr_service = HybridOCRService()
    print(f"👁️ Vision Model configured: {ocr_service.vision_model}")

    # Directory esempi
    examples_dir = Path(__file__).parent.parent / "examples"
    if not examples_dir.exists():
        print(f"❌ Directory examples non trovata: {examples_dir}")
        return

    files = [f for f in examples_dir.iterdir() if f.is_file() and f.name != ".DS_Store"]
    print(f"📂 Trovati {len(files)} file in examples/")

    for file_path in files:
        print(f"\n📄 Processing: {file_path.name}")
        try:
            result = await ocr_service.process_file(file_path)

            print(f"   ✅ Success!")
            print(f"   🛠️ Method: {result.get('method')} ({result.get('model')})")
            print(f"   📄 Pages: {result.get('pages')}")

            content = result.get("content", "")
            preview = content[:200].replace("\n", " ") if content else "No content"
            print(f"   📝 Content Preview: {preview}...")

            if result.get("reasoning"):
                print(f"   🧠 Reasoning: {result.get('reasoning')[:100]}...")

        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n🎉 Test completati.")


if __name__ == "__main__":
    asyncio.run(main())
