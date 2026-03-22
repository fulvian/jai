"""
Script per scaricare i modelli di embedding in locale.

Scarica BAAI/bge-m3 nella directory models/ per uso offline/isolato.
"""

import sys
from pathlib import Path

# Aggiunge src al path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from me4brain.embeddings import get_embedding_service
from me4brain.utils.logging import configure_logging

configure_logging()


def main():
    print("🚀 Inizio download modelli embedding...")

    # Inizializzare il servizio forza il download se non presente in cache
    try:
        service = get_embedding_service()
        model_path = service.cache_dir / "models--BAAI--bge-m3"

        print("\n✅ Modello BGE-M3 scaricato/verificato con successo.")
        print(f"📂 Cache path: {service.cache_dir}")
        print(f"🔌 Device in uso: {service.device}")

    except Exception as e:
        print(f"\n❌ Errore durante il download: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
