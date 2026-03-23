"""Test Conflict Resolution Module."""

from datetime import UTC, datetime, timedelta

import pytest

from me4brain.core.conflict import (
    ConflictResolver,
    ConflictSource,
)


class TestConflictResolver:
    """Test suite per Conflict Resolution."""

    @pytest.fixture
    def resolver(self) -> ConflictResolver:
        """Crea un resolver per i test."""
        return ConflictResolver(default_strategy="recency")

    @pytest.fixture
    def recent_source(self) -> ConflictSource:
        """Crea una fonte recente."""
        return ConflictSource(
            source_type="episodic",
            content="Informazione recente",
            score=0.8,
            timestamp=datetime.now(UTC) - timedelta(hours=1),
        )

    @pytest.fixture
    def old_source(self) -> ConflictSource:
        """Crea una fonte vecchia."""
        return ConflictSource(
            source_type="semantic",
            content="Informazione vecchia",
            score=0.9,
            timestamp=datetime.now(UTC) - timedelta(days=7),
        )

    def test_detect_conflict_both_present(
        self,
        resolver: ConflictResolver,
        recent_source: ConflictSource,
        old_source: ConflictSource,
    ) -> None:
        """Test rilevamento conflitto con entrambe le fonti."""
        has_conflict = resolver.detect_conflict(recent_source, old_source)
        assert has_conflict is True

    def test_detect_conflict_same_content(
        self,
        resolver: ConflictResolver,
    ) -> None:
        """Test nessun conflitto se contenuti identici."""
        source1 = ConflictSource(
            source_type="episodic",
            content="Stesso contenuto",
            score=0.8,
        )
        source2 = ConflictSource(
            source_type="semantic",
            content="Stesso contenuto",
            score=0.9,
        )
        has_conflict = resolver.detect_conflict(source1, source2)
        assert has_conflict is False

    def test_detect_conflict_missing_source(
        self,
        resolver: ConflictResolver,
        recent_source: ConflictSource,
    ) -> None:
        """Test nessun conflitto se manca una fonte."""
        has_conflict = resolver.detect_conflict(recent_source, None)
        assert has_conflict is False

    def test_resolve_by_recency(
        self,
        resolver: ConflictResolver,
        recent_source: ConflictSource,
        old_source: ConflictSource,
    ) -> None:
        """Test risoluzione per recency: vince il più recente."""
        resolution = resolver.resolve(recent_source, old_source, strategy="recency")

        assert resolution.winner == recent_source
        assert resolution.loser == old_source
        assert resolution.strategy == "recency"
        assert resolution.confidence > 0.5

    def test_resolve_by_confidence(
        self,
        resolver: ConflictResolver,
        recent_source: ConflictSource,
        old_source: ConflictSource,
    ) -> None:
        """Test risoluzione per confidence: vince lo score più alto."""
        resolution = resolver.resolve(recent_source, old_source, strategy="confidence")

        # old_source ha score più alto (0.9 vs 0.8)
        assert resolution.winner == old_source
        assert resolution.loser == recent_source
        assert resolution.strategy == "confidence"

    def test_resolve_by_authority(
        self,
        resolver: ConflictResolver,
        recent_source: ConflictSource,
        old_source: ConflictSource,
    ) -> None:
        """Test risoluzione per authority: vince la fonte più autorevole."""
        resolution = resolver.resolve(recent_source, old_source, strategy="authority")

        # semantic ha authority più alta (1.0 vs 0.8)
        assert resolution.winner == old_source
        assert resolution.strategy == "authority"

    def test_resolve_by_merge(
        self,
        resolver: ConflictResolver,
        recent_source: ConflictSource,
        old_source: ConflictSource,
    ) -> None:
        """Test risoluzione per merge: combina le informazioni."""
        resolution = resolver.resolve(recent_source, old_source, strategy="merged")

        assert resolution.strategy == "merged"
        assert resolution.merged_content is not None
        assert "Informazione" in resolution.merged_content

    def test_get_age_hours_with_timestamp(
        self,
        resolver: ConflictResolver,
    ) -> None:
        """Test calcolo età in ore."""
        now = datetime.now(UTC)
        timestamp = now - timedelta(hours=5)

        age = resolver._get_age_hours(timestamp, now)
        assert abs(age - 5.0) < 0.01  # Tolleranza

    def test_get_age_hours_without_timestamp(
        self,
        resolver: ConflictResolver,
    ) -> None:
        """Test età con timestamp None (molto vecchio)."""
        now = datetime.now(UTC)
        age = resolver._get_age_hours(None, now)
        assert age > 100000  # Molto grande
