"""Conflict Resolution Module.

Gestisce conflitti tra risultati di Vector Search e Graph Traversal.
Implementa Recency Bias come strategia primaria di risoluzione.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class ConflictSource(BaseModel):
    """Rappresenta una fonte di informazione in conflitto."""

    source_type: str  # "episodic", "semantic", "procedural"
    content: str
    score: float
    timestamp: datetime | None = None
    entity_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConflictResolution(BaseModel):
    """Risultato della risoluzione di un conflitto."""

    winner: ConflictSource
    loser: ConflictSource
    strategy: str  # "recency", "confidence", "authority", "merged"
    confidence: float
    explanation: str
    merged_content: str | None = None  # Se strategy == "merged"


class ConflictResolver:
    """Risolve conflitti tra risultati di retrieval.

    Strategie implementate:
    1. Recency Bias: preferisce informazioni più recenti
    2. Confidence: preferisce score più alto
    3. Authority: preferisce fonte più autorevole
    4. Merged: combina le informazioni
    """

    # Pesi per le fonti (authority)
    SOURCE_AUTHORITY: dict[str, float] = {
        "semantic": 1.0,  # Knowledge graph = alta autorità
        "episodic": 0.8,  # Memoria episodica = media-alta
        "procedural": 0.9,  # Procedure = alta (verificate)
        "working": 0.6,  # Working memory = più bassa
    }

    # Soglie
    SCORE_DIFF_THRESHOLD = 0.15  # Differenza minima per preferire per score
    RECENCY_HOURS_THRESHOLD = 24  # Ore entro cui recency ha priorità

    def __init__(
        self,
        default_strategy: str = "recency",
    ) -> None:
        """Inizializza il resolver.

        Args:
            default_strategy: Strategia di default ("recency", "confidence", "authority")
        """
        self.default_strategy = default_strategy

    def detect_conflict(
        self,
        vector_result: ConflictSource | None,
        graph_result: ConflictSource | None,
        similarity_threshold: float = 0.7,
    ) -> bool:
        """Rileva se c'è un conflitto tra i risultati.

        Un conflitto esiste quando:
        - Entrambe le fonti hanno contenuto
        - I contenuti sono semanticamente diversi
        - Entrambi hanno score significativo

        Args:
            vector_result: Risultato da vector search
            graph_result: Risultato da graph traversal
            similarity_threshold: Soglia di similarità per considerare "stesso" contenuto

        Returns:
            True se c'è conflitto
        """
        if vector_result is None or graph_result is None:
            return False

        if not vector_result.content or not graph_result.content:
            return False

        # Contenuti identici = no conflitto
        if vector_result.content.strip() == graph_result.content.strip():
            return False

        # Entrambi devono avere score significativo
        if vector_result.score < 0.5 or graph_result.score < 0.5:
            return False

        # TODO: In futuro, usare embedding similarity per rilevare
        # conflitti semantici (stesso topic, info diverse)

        # Per ora, assumiamo conflitto se contenuti diversi e score alti
        return True

    def resolve(
        self,
        vector_result: ConflictSource,
        graph_result: ConflictSource,
        strategy: str | None = None,
    ) -> ConflictResolution:
        """Risolve un conflitto tra due fonti.

        Args:
            vector_result: Risultato da vector search
            graph_result: Risultato da graph traversal
            strategy: Strategia da usare (default: self.default_strategy)

        Returns:
            ConflictResolution con il vincitore e la spiegazione
        """
        strategy = strategy or self.default_strategy

        if strategy == "recency":
            return self._resolve_by_recency(vector_result, graph_result)
        elif strategy == "confidence":
            return self._resolve_by_confidence(vector_result, graph_result)
        elif strategy == "authority":
            return self._resolve_by_authority(vector_result, graph_result)
        elif strategy == "merged":
            return self._resolve_by_merge(vector_result, graph_result)
        else:
            # Fallback a recency
            return self._resolve_by_recency(vector_result, graph_result)

    def _resolve_by_recency(
        self,
        vector_result: ConflictSource,
        graph_result: ConflictSource,
    ) -> ConflictResolution:
        """Risolve preferendo l'informazione più recente.

        Recency Bias: informazioni più recenti sono spesso più accurate.
        """
        now = datetime.now(UTC)

        # Calcola età in ore
        vector_age = self._get_age_hours(vector_result.timestamp, now)
        graph_age = self._get_age_hours(graph_result.timestamp, now)

        # Preferisci il più recente
        if vector_age < graph_age:
            winner, loser = vector_result, graph_result
            diff = graph_age - vector_age
        else:
            winner, loser = graph_result, vector_result
            diff = vector_age - graph_age

        # Calcola confidence basata sulla differenza di età
        # Più grande la differenza, più confident siamo
        confidence = min(0.95, 0.6 + (diff / 168))  # 168h = 1 settimana

        logger.info(
            "conflict_resolved_recency",
            winner_source=winner.source_type,
            winner_age_hours=self._get_age_hours(winner.timestamp, now),
            loser_age_hours=self._get_age_hours(loser.timestamp, now),
            confidence=confidence,
        )

        return ConflictResolution(
            winner=winner,
            loser=loser,
            strategy="recency",
            confidence=confidence,
            explanation=(f"Preferito {winner.source_type} perché più recente (diff: {diff:.1f}h)"),
        )

    def _resolve_by_confidence(
        self,
        vector_result: ConflictSource,
        graph_result: ConflictSource,
    ) -> ConflictResolution:
        """Risolve preferendo lo score più alto."""
        if vector_result.score > graph_result.score:
            winner, loser = vector_result, graph_result
        else:
            winner, loser = graph_result, vector_result

        score_diff = winner.score - loser.score
        confidence = min(0.95, 0.5 + score_diff)

        return ConflictResolution(
            winner=winner,
            loser=loser,
            strategy="confidence",
            confidence=confidence,
            explanation=(
                f"Preferito {winner.source_type} per score più alto "
                f"({winner.score:.2f} vs {loser.score:.2f})"
            ),
        )

    def _resolve_by_authority(
        self,
        vector_result: ConflictSource,
        graph_result: ConflictSource,
    ) -> ConflictResolution:
        """Risolve preferendo la fonte più autorevole."""
        vector_auth = self.SOURCE_AUTHORITY.get(vector_result.source_type, 0.5)
        graph_auth = self.SOURCE_AUTHORITY.get(graph_result.source_type, 0.5)

        if vector_auth > graph_auth:
            winner, loser = vector_result, graph_result
            auth_diff = vector_auth - graph_auth
        else:
            winner, loser = graph_result, vector_result
            auth_diff = graph_auth - vector_auth

        confidence = min(0.9, 0.6 + auth_diff)

        return ConflictResolution(
            winner=winner,
            loser=loser,
            strategy="authority",
            confidence=confidence,
            explanation=(
                f"Preferito {winner.source_type} per maggiore autorità "
                f"({self.SOURCE_AUTHORITY.get(winner.source_type, 0.5):.1f})"
            ),
        )

    def _resolve_by_merge(
        self,
        vector_result: ConflictSource,
        graph_result: ConflictSource,
    ) -> ConflictResolution:
        """Combina le informazioni da entrambe le fonti.

        Utile quando entrambe contengono informazioni parziali complementari.
        """
        # Determina quale mettere prima (per authority)
        vector_auth = self.SOURCE_AUTHORITY.get(vector_result.source_type, 0.5)
        graph_auth = self.SOURCE_AUTHORITY.get(graph_result.source_type, 0.5)

        if graph_auth >= vector_auth:
            primary, secondary = graph_result, vector_result
        else:
            primary, secondary = vector_result, graph_result

        # Merge semplice: combina i contenuti
        merged = (
            f"{primary.content}\n\n"
            f"[Informazione aggiuntiva da {secondary.source_type}]: "
            f"{secondary.content}"
        )

        # Confidence è la media ponderata
        avg_confidence = primary.score * 0.6 + secondary.score * 0.4

        return ConflictResolution(
            winner=primary,
            loser=secondary,
            strategy="merged",
            confidence=avg_confidence,
            explanation="Informazioni combinate da entrambe le fonti",
            merged_content=merged,
        )

    def _get_age_hours(
        self,
        timestamp: datetime | None,
        now: datetime,
    ) -> float:
        """Calcola l'età in ore di un timestamp."""
        if timestamp is None:
            # Se non abbiamo timestamp, assumiamo molto vecchio
            return 999999.0

        # Assicurati che timestamp sia timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        diff = now - timestamp
        return diff.total_seconds() / 3600


# Singleton
_resolver: ConflictResolver | None = None


def get_conflict_resolver() -> ConflictResolver:
    """Ottiene l'istanza singleton del resolver."""
    global _resolver
    if _resolver is None:
        _resolver = ConflictResolver()
    return _resolver
