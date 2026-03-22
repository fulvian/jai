"""Module: Embeddings Service.

Espone l'interfaccia unficata per i modelli di embedding.
Default: BAAI/bge-m3.
"""

from me4brain.embeddings.bge_m3 import BGEM3Service, get_embedding_service

__all__ = ["BGEM3Service", "get_embedding_service"]
