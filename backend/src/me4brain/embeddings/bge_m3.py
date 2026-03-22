"""
BGE-M3 Embedding Service.

Wrapper per il modello BAAI/bge-m3 usando SentenceTransformers.
Supporta:
- Multilingualità (IT/EN)
- Dense Embeddings (1024 dim)
- Sparse Embeddings (Lexical Weights) - Future expansion
- Multi-Vector (ColBERT) - Future expansion

Running in-process su CPU/MPS (Apple Silicon optimized).

NOTE: BGE-M3 always returns L2-normalized embeddings internally.
Expected cosine similarity scores:
- Excellent match: 0.70-0.85
- Good match: 0.55-0.70
- Fair match: 0.45-0.55
- Weak match: 0.30-0.45
- Irrelevant: <0.30
"""

import os
from pathlib import Path
from typing import List, Union

import torch
from sentence_transformers import SentenceTransformer
from structlog import get_logger

log = get_logger()


class BGEM3Service:
    """Service per generare embedding usando BAAI/bge-m3."""

    # Configurazione Modello
    MODEL_NAME = "BAAI/bge-m3"
    MODEL_CACHE_DIR = Path("models").absolute()

    def __init__(self, use_fc: bool = True):
        """
        Inizializza il modello BGE-M3.

        Args:
            use_fp16: Se True, usa precisione float16 (su GPU/MPS).
        """
        self.device = self._get_device()
        self.cache_dir = self.MODEL_CACHE_DIR

        log.info(
            "Initializing BGE-M3 Embedding Service",
            device=self.device,
            cache=str(self.cache_dir),
        )

        # Assicura che la directory modelli esista
        self.cache_dir.mkdir(exist_ok=True, parents=True)

        # Check for manual download directory
        manual_path = Path("models/bge-m3-manual").absolute()
        model_path = (
            str(manual_path)
            if manual_path.exists() and any(manual_path.iterdir())
            else self.MODEL_NAME
        )

        if manual_path.exists():
            log.info(
                "Found manual model directory, using local weights",
                path=str(manual_path),
            )
        else:
            log.info(
                "Manual directory not found/empty, using HF Cache",
                cache=str(self.cache_dir),
            )

        try:
            # Caricamento Modello
            # use_auth_token=False perché BGE-M3 è pubblico
            self.model = SentenceTransformer(
                model_path,
                cache_folder=str(self.cache_dir) if model_path == self.MODEL_NAME else None,
                device=self.device,
            )

            # Ottimizzazioni
            if self.device != "cpu":
                self.model.half()  # Use fp16 for speed/memory on MPS/CUDA

            log.info(
                "BGE-M3 Model loaded successfully",
                config=self.model.get_sentence_embedding_dimension(),
            )

        except Exception as e:
            log.error("Failed to load BGE-M3 model", error=str(e))
            raise RuntimeError(f"Could not load BGE-M3: {e}")

    def _get_device(self) -> str:
        """Determina il device migliore (Settings > MPS > CUDA > CPU)."""
        from me4brain.config.settings import get_settings

        settings = get_settings()
        if settings.embedding_device:
            return settings.embedding_device

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    # Retrieval query prefix per migliorare precision (+10-20% NDCG secondo research)
    QUERY_PREFIX = "Represent this query for retrieval: "

    def embed_query(self, text: str) -> List[float]:
        """Genera embedding per una singola query di retrieval.

        Applica prompt engineering raccomandato per BGE-M3:
        "Represent this query for retrieval: <query>"
        """
        # Applica prefix per query retrieval (best practice BGE)
        prefixed_text = f"{self.QUERY_PREFIX}{text}"

        emb = self.model.encode(
            prefixed_text,
            convert_to_tensor=True,
            normalize_embeddings=True,  # BGE-M3 normalizes internally anyway
            show_progress_bar=False,
        )

        # Converte in lista float
        return emb.cpu().tolist()  # type: ignore

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Genera embedding per una lista di documenti (senza prefix)."""
        if not texts:
            return []

        embs = self.model.encode(
            texts,
            batch_size=16,
            convert_to_tensor=True,
            normalize_embeddings=True,  # BGE-M3 normalizes internally anyway
            show_progress_bar=False,
        )

        return embs.cpu().tolist()  # type: ignore

    def embed_document(self, text: str) -> List[float]:
        """Genera embedding per un singolo documento.

        Args:
            text: Il testo del documento da embedded

        Returns:
            Lista di float rappresentante l'embedding del documento
        """
        embeddings = self.embed_documents([text])
        return embeddings[0] if embeddings else []

    # Funzioni accessorie per il futuro (Sparse/ColBERT)
    # def embed_sparse(...)
    # def embed_colbert(...)

    async def embed_query_async(self, text: str) -> List[float]:
        """Async wrapper for embed_query using thread pool.

        More efficient for hybrid router which calls embed for each tool.

        Args:
            text: Text to embed

        Returns:
            List of floats (1024 dim embedding)
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)

    async def embed_documents_async(self, texts: List[str]) -> List[List[float]]:
        """Async wrapper for embed_documents using thread pool.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)

    async def embed_document_async(self, text: str) -> List[float]:
        """Async wrapper for embed_document using thread pool.

        Args:
            text: Text to embed

        Returns:
            List of floats (1024 dim embedding)
        """
        import asyncio

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(None, self.embed_documents, [text])
        return embeddings[0] if embeddings else []


# Singleton Instance
_embedding_service: Union[BGEM3Service, None] = None


def get_embedding_service() -> BGEM3Service:
    """Ottiene l'istanza singleton del servizio embedding."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = BGEM3Service()
    return _embedding_service
