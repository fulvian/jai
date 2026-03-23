"""BM25 Lexical Search Module.

Implementa BM25 (Best Matching 25) per retrieval lessicale.
Usato come componente nel sistema Hybrid Search per migliorare
il recall, specialmente per query con keyword specifiche.

BM25 è un ranking function usata in information retrieval
che tiene conto della lunghezza del documento e della
frequenza dei termini nella collezione.

Riferimento: Robertson & Zaragoza (2009) - "The Probabilistic Relevance Framework: BM25 and Beyond"
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class BM25Indexer:
    """BM25 indexer per document retrieval lessicale.

    Implementa BM25Okapi con ottimizzazioni per usage pattern tipici:
    - Lazy initialization
    - Batch indexing
    - Token normalization

    BM25 Parameters (configurabili):
    - k1: Term frequency saturation (default: 1.5)
    - b: Length normalization (default: 0.75)
    - avgdl: Average document length (calcolato automaticamente)
    """

    DEFAULT_K1 = 1.5
    DEFAULT_B = 0.75

    def __init__(
        self,
        k1: float | None = None,
        b: float | None = None,
    ) -> None:
        """Initialize BM25 indexer.

        Args:
            k1: Term frequency saturation parameter. Higher values
                give more weight to term frequency. Typical: 1.2-2.0
            b: Length normalization parameter. Controls how much
                document length affects scoring. Typical: 0.5-0.75
        """
        self._k1 = k1 or self.DEFAULT_K1
        self._b = b or self.DEFAULT_B

        # Document storage
        self._ids: list[str] = []
        self._corpus: list[list[str]] = []  # Tokenized documents
        self._doc_lengths: list[int] = []
        self._avgdl: float = 0.0

        # IDF cache
        self._idf: dict[str, float] = {}
        self._indexed: bool = False

        # Statistics
        self._total_docs: int = 0
        self._total_terms: int = 0

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into terms.

        Applies:
        - Lowercasing
        - Word boundary splitting
        - Alphanumeric extraction

        Args:
            text: Input text

        Returns:
            List of lowercase tokens
        """
        if not text:
            return []

        # Lowercase and split on non-alphanumeric
        tokens = re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())

        # Filter very short tokens
        return [t for t in tokens if len(t) >= 2]

    def _compute_idf(self) -> dict[str, float]:
        """Compute IDF (Inverse Document Frequency) for all terms.

        Uses the BM25Okapi formula:
        IDF(t) = log((N - n_t + 0.5) / (n_t + 0.5) + 1)

        Returns:
            Dict mapping term to IDF score
        """
        import math

        N = len(self._corpus)
        if N == 0:
            return {}

        # Count document frequencies
        df: dict[str, int] = {}
        for doc in self._corpus:
            seen_terms: set[str] = set()
            for term in doc:
                if term not in seen_terms:
                    df[term] = df.get(term, 0) + 1
                    seen_terms.add(term)

        # Compute IDF using BM25Okapi formula
        idf: dict[str, float] = {}
        for term, n_t in df.items():
            # BM25Okapi IDF formula with smoothing
            idf[term] = math.log((N - n_t + 0.5) / (n_t + 0.5) + 1)

    def add_documents(self, documents: list[tuple[str, str]]) -> None:
        """Add documents to existing index (incremental indexing).

        For efficient bulk indexing, prefer index() which rebuilds entirely.
        This method is useful for adding a small number of documents.

        Args:
            documents: List of (id, text) tuples to add
        """
        if not documents:
            return

        # For now, rebuild index (optimization possible later)
        if self._indexed:
            # Merge with existing
            existing = list(zip(self._ids, [" ".join(d) for d in self._corpus], strict=True))
            all_docs = existing + documents
            self.index(all_docs)
        else:
            self.index(documents)

    def search(
        self,
        query: str,
        top_k: int = 50,
        min_score: float = 0.0,
    ) -> list[tuple[str, float]]:
        """Search for documents matching query using BM25.

        Args:
            query: Search query
            top_k: Number of top results to return
            min_score: Minimum BM25 score threshold

        Returns:
            List of (document_id, score) tuples sorted by score descending
        """
        if not self._indexed:
            logger.warning("bm25_search_not_indexed")
            return []

        if not query:
            return []

        # Tokenize query
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        # Compute BM25 score for each document
        scores: dict[int, float] = {}

        for doc_idx, doc in enumerate(self._corpus):
            score = self._bm25_score(doc, query_terms)
            if score > min_score:
                scores[doc_idx] = score

        # Sort by score and return top-k
        sorted_results = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        return [(self._ids[idx], score) for idx, score in sorted_results]

    def _bm25_score(
        self,
        doc: list[str],
        query_terms: list[str],
    ) -> float:
        """Compute BM25 score for a document given query terms.

        BM25 Formula:
        score(D, Q) = sum over q in Q of:
            IDF(q) * (f(q, D) * (k1 + 1)) / (f(q, D) + k1 * (1 - b + b * |D|/avgdl))

        Args:
            doc: Tokenized document
            query_terms: Tokenized query

        Returns:
            BM25 score
        """
        doc_len = len(doc)
        score = 0.0

        # Count term frequencies in document
        term_freq: dict[str, int] = {}
        for term in doc:
            term_freq[term] = term_freq.get(term, 0) + 1

        for term in query_terms:
            if term not in self._idf:
                # Term not in corpus - skip
                continue

            tf = term_freq.get(term, 0)
            if tf == 0:
                continue

            idf = self._idf[term]

            # BM25 scoring
            numerator = tf * (self._k1 + 1)
            denominator = tf + self._k1 * (1 - self._b + self._b * doc_len / max(self._avgdl, 1))

            score += idf * (numerator / denominator)

        return score

    def get_stats(self) -> dict:
        """Return index statistics.

        Returns:
            Dict with index stats
        """
        return {
            "document_count": self._total_docs,
            "unique_terms": len(self._idf),
            "total_terms": self._total_terms,
            "avg_doc_length": round(self._avgdl, 1),
            "indexed": self._indexed,
            "k1": self._k1,
            "b": self._b,
        }


class LexicalSearchService:
    """Service per BM25 lexical search nel contesto del Session Graph.

    Gestisce l'indicizzazione e ricerca di sessioni e turns
    usando BM25 per hybrid retrieval con i vector embeddings.

    Usage:
        service = LexicalSearchService()
        service.index_sessions([("sess_1", "Session about Python"), ...])
        results = service.search("Python programming")
    """

    # Default number of results from BM25 to pass to RRF
    DEFAULT_TOP_K = 50

    def __init__(self) -> None:
        """Initialize lexical search service."""
        self._session_index: BM25Indexer | None = None
        self._turn_index: BM25Indexer | None = None

        # Separate indexes for sessions and turns
        self._session_index = BM25Indexer()
        self._turn_index = BM25Indexer()

        logger.info("lexical_search_service_initialized")

    def index_sessions(
        self,
        sessions: list[tuple[str, str]],
    ) -> None:
        """Index sessions for lexical search.

        Args:
            sessions: List of (session_id, text) tuples.
                     text should be concatenation of title + turn previews.
        """
        if not sessions:
            return

        self._session_index = BM25Indexer()
        self._session_index.index(sessions)

        logger.info(
            "lexical_search_sessions_indexed",
            count=len(sessions),
        )

    def index_turns(
        self,
        turns: list[tuple[str, str]],
    ) -> None:
        """Index turns for lexical search.

        Args:
            turns: List of (turn_id, content) tuples.
        """
        if not turns:
            return

        self._turn_index = BM25Indexer()
        self._turn_index.index(turns)

        logger.info(
            "lexical_search_turns_indexed",
            count=len(turns),
        )

    def search_sessions(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[tuple[str, float]]:
        """Search indexed sessions by query.

        Args:
            query: Search query
            top_k: Number of results (default: 50)

        Returns:
            List of (session_id, score) tuples
        """
        if self._session_index is None:
            return []

        top_k = top_k or self.DEFAULT_TOP_K
        return self._session_index.search(query, top_k=top_k)

    def search_turns(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[tuple[str, float]]:
        """Search indexed turns by query.

        Args:
            query: Search query
            top_k: Number of results (default: 50)

        Returns:
            List of (turn_id, score) tuples
        """
        if self._turn_index is None:
            return []

        top_k = top_k or self.DEFAULT_TOP_K
        return self._turn_index.search(query, top_k=top_k)

    def search_combined(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[tuple[str, float]]:
        """Search both sessions and turns, combining results.

        Args:
            query: Search query
            top_k: Number of results (default: 50)

        Returns:
            List of (id, score) tuples. IDs prefixed with "session:" or "turn:"
        """
        top_k = top_k or self.DEFAULT_TOP_K

        results: dict[str, float] = {}

        # Search sessions
        if self._session_index is not None:
            for session_id, score in self._session_index.search(query, top_k=top_k):
                results[f"session:{session_id}"] = score

        # Search turns
        if self._turn_index is not None:
            for turn_id, score in self._turn_index.search(query, top_k=top_k):
                results[f"turn:{turn_id}"] = score

        # Sort by score
        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        return sorted_results

    def get_stats(self) -> dict:
        """Return service statistics.

        Returns:
            Dict with stats for all indexes
        """
        return {
            "session_index": self._session_index.get_stats() if self._session_index else None,
            "turn_index": self._turn_index.get_stats() if self._turn_index else None,
        }


# Singleton instance
_lexical_search_service: LexicalSearchService | None = None


def get_lexical_search_service() -> LexicalSearchService:
    """Get the global lexical search service instance."""
    global _lexical_search_service
    if _lexical_search_service is None:
        _lexical_search_service = LexicalSearchService()
    return _lexical_search_service
