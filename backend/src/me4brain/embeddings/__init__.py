"""Module: Embeddings Service.

Espone l'interfaccia unficata per i modelli di embedding.
Default: BAAI/bge-m3.
"""

from me4brain.embeddings.bge_m3 import BGEM3Service, get_embedding_service
from me4brain.embeddings.embedding_cache import (
    EmbeddingCache,
    get_embedding_cache,
    set_embedding_cache,
)

__all__ = [
    "BGEM3Service",
    "get_embedding_service",
    "EmbeddingCache",
    "get_embedding_cache",
    "set_embedding_cache",
]
