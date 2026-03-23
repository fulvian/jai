"""
BGE-M3 Embedding Service.

Wrapper per il modello BAAI/bge-m3 usando SentenceTransformers.
Supporta:
- Multilingualità (IT/EN)
- Dense Embeddings (1024 dim)
- Sparse Embeddings (Lexical Weights) - Future expansion
- Multi-Vector (ColBERT) - Future expansion
- Embedding caching (L1 memory + L2 Redis)
- Batch processing for efficiency

Running in-process su CPU/MPS (Apple Silicon optimized).

NOTE: BGE-M3 always returns L2-normalized embeddings internally.
Expected cosine similarity scores:
- Excellent match: 0.70-0.85
- Good match: 0.55-0.70
- Fair match: 0.45-0.55
- Weak match: 0.30-0.45
- Irrelevant: <0.30
"""

from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from structlog import get_logger

from me4brain.embeddings.embedding_cache import EmbeddingCache, get_embedding_cache

log = get_logger()


class BGEM3Service:
    """Service per generare embedding usando BAAI/bge-m3.

    Features:
    - BGE-M3 model with CPU/MPS optimization
    - Multi-tier embedding cache (L1 + L2)
    - Batch embedding support
    - Async wrappers for all operations
    """

    # Configurazione Modello
    MODEL_NAME = "BAAI/bge-m3"
    MODEL_CACHE_DIR = Path("models").absolute()

    # Batch processing settings
    DEFAULT_BATCH_SIZE = 32
    MAX_BATCH_SIZE = 64

    def __init__(
        self,
        use_fp16: bool = True,
        cache: EmbeddingCache | None = None,
    ):
        """
        Inizializza il modello BGE-M3.

        Args:
            use_fp16: Se True, usa precisione float16 (su GPU/MPS).
            cache: EmbeddingCache instance (default: global singleton).
        """
        self.device = self._get_device()
        self.cache_dir = self.MODEL_CACHE_DIR
        self._cache = cache

        log.info(
            "Initializing BGE-M3 Embedding Service",
            device=self.device,
            cache=str(self.cache_dir),
            use_fp16=use_fp16,
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
            if use_fp16 and self.device != "cpu":
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

    def embed_query(self, text: str) -> list[float]:
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

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
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

    def embed_document(self, text: str) -> list[float]:
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

    # =========================================================================
    # Embedding Cache Integration
    # =========================================================================

    @property
    def cache(self) -> EmbeddingCache:
        """Get the embedding cache (lazy initialization)."""
        if self._cache is None:
            self._cache = get_embedding_cache()
        return self._cache

    async def embed_query_cached(self, text: str) -> list[float]:
        """Generate embedding for query with caching.

        Args:
            text: Query text

        Returns:
            Embedding vector as list of floats
        """
        cached = await self.cache.get(text)
        if cached is not None:
            return cached.tolist()

        embedding = await self.embed_query_async(text)
        await self.cache.set(text, np.array(embedding))
        return embedding

    async def embed_document_cached(self, text: str) -> list[float]:
        """Generate embedding for document with caching.

        Args:
            text: Document text

        Returns:
            Embedding vector as list of floats
        """
        cached = await self.cache.get(text)
        if cached is not None:
            return cached.tolist()

        embedding = self.embed_document(text)
        await self.cache.set(text, np.array(embedding))
        return embedding

    async def embed_documents_cached(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        """Generate embeddings for multiple documents with caching.

        Implements cache-aside pattern: checks cache first, computes missing,
        then stores in cache.

        Args:
            texts: List of document texts
            batch_size: Processing batch size (default: 32)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        batch_size = min(batch_size or self.DEFAULT_BATCH_SIZE, self.MAX_BATCH_SIZE)

        # Check cache first
        cached_results: dict[int, np.ndarray] = {}
        texts_to_compute: list[tuple[int, str]] = []

        for idx, text in enumerate(texts):
            cached = await self.cache.get(text)
            if cached is not None:
                cached_results[idx] = cached
            else:
                texts_to_compute.append((idx, text))

        # Compute missing embeddings
        if texts_to_compute:
            # Extract texts in order
            indices = [t[0] for t in texts_to_compute]
            missing_texts = [t[1] for t in texts_to_compute]

            # Process in batches
            for i in range(0, len(missing_texts), batch_size):
                batch_texts = missing_texts[i : i + batch_size]
                batch_indices = indices[i : i + batch_size]

                # Encode batch
                batch_embeddings = self.model.encode(
                    batch_texts,
                    batch_size=len(batch_texts),
                    convert_to_tensor=False,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )

                # Store in cache and collect results
                for idx, text, embedding in zip(batch_indices, batch_texts, batch_embeddings):
                    embedding_array = embedding.astype(np.float32)
                    await self.cache.set(text, embedding_array)
                    cached_results[idx] = embedding_array

        # Sort by original index and convert to lists
        sorted_results = sorted(cached_results.items(), key=lambda x: x[0])
        return [emb.tolist() for _, emb in sorted_results]

    # =========================================================================
    # Batch Embedding Operations
    # =========================================================================

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int | None = None,
        use_cache: bool = True,
    ) -> list[list[float]]:
        """Batch embed multiple texts for efficiency.

        Args:
            texts: List of texts to embed
            batch_size: Processing batch size (default: 32, max: 64)
            use_cache: Whether to use embedding cache

        Returns:
            List of embeddings in same order as input
        """
        if not texts:
            return []

        batch_size = min(batch_size or self.DEFAULT_BATCH_SIZE, self.MAX_BATCH_SIZE)

        if use_cache:
            return await self.embed_documents_cached(texts, batch_size)

        # Direct batch encoding without cache
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self.model.encode(
                batch,
                batch_size=len(batch),
                convert_to_tensor=False,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            all_embeddings.extend(embeddings.tolist())

        return all_embeddings

    async def embed_batch_async(
        self,
        texts: list[str],
        batch_size: int | None = None,
        use_cache: bool = True,
    ) -> list[list[float]]:
        """Async wrapper for embed_batch.

        Args:
            texts: List of texts to embed
            batch_size: Processing batch size
            use_cache: Whether to use embedding cache

        Returns:
            List of embeddings
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: asyncio.run(self.embed_batch(texts, batch_size, use_cache))
        )

    async def embed_query_async(self, text: str) -> list[float]:
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

    async def embed_query_async_cached(self, text: str) -> list[float]:
        """Async wrapper for embed_query with caching.

        Args:
            text: Text to embed

        Returns:
            List of floats (1024 dim embedding)
        """
        cached = await self.cache.get(text)
        if cached is not None:
            return cached.tolist()

        embedding = await self.embed_query_async(text)
        await self.cache.set(text, np.array(embedding))
        return embedding

    async def embed_documents_async(self, texts: list[str]) -> list[list[float]]:
        """Async wrapper for embed_documents using thread pool.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)

    async def embed_document_async(self, text: str) -> list[float]:
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
_embedding_service: BGEM3Service | None = None


def get_embedding_service() -> BGEM3Service:
    """Ottiene l'istanza singleton del servizio embedding."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = BGEM3Service()
    return _embedding_service
