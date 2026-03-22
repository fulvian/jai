"""Memory Decay Module - Domain-Aware Time Decay.

Implementa decay temporale differenziato per dominio per evitare
retrieval di dati obsoleti nei domini volatili.

Strategy:
- VOLATILE (sports, finance, weather): Decay aggressivo, tool-first
- SEMI_VOLATILE (workspace, science): Decay moderato
- STABLE (medical, knowledge): Decay lento
- PERMANENT (preferences): No decay
"""

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic import BaseModel, Field

from me4brain.core.interfaces import DomainVolatility

logger = structlog.get_logger(__name__)


class DomainDecayConfig(BaseModel):
    """Configurazione decay per un dominio specifico."""

    volatility: DomainVolatility
    max_age_hours: int | None = Field(
        None,
        description="Età massima in ore. None = no hard limit",
    )
    decay_rate: float = Field(
        0.01,
        description="Rate decay esponenziale (0.0-1.0)",
    )
    preserve_patterns: bool = Field(
        True,
        description="Se True, estrae pattern prima di eliminare dati",
    )
    tool_first: bool = Field(
        False,
        description="Se True, sempre chiama tool prima di consultare memoria",
    )


# Configurazione decay per dominio
DOMAIN_DECAY_CONFIGS: dict[str, DomainDecayConfig] = {
    # Volatile: dati scadono rapidamente
    "sports_nba": DomainDecayConfig(
        volatility=DomainVolatility.VOLATILE,
        max_age_hours=24,
        decay_rate=0.3,
        preserve_patterns=True,
        tool_first=True,
    ),
    "finance_crypto": DomainDecayConfig(
        volatility=DomainVolatility.VOLATILE,
        max_age_hours=12,
        decay_rate=0.25,
        preserve_patterns=True,
        tool_first=True,
    ),
    "geo_weather": DomainDecayConfig(
        volatility=DomainVolatility.VOLATILE,
        max_age_hours=6,
        decay_rate=0.4,
        preserve_patterns=False,
        tool_first=True,
    ),
    "duckduckgo_search": DomainDecayConfig(
        volatility=DomainVolatility.VOLATILE,
        max_age_hours=1,
        decay_rate=0.5,
        preserve_patterns=False,
        tool_first=True,
    ),
    # Semi-volatile: decay moderato
    "google_workspace": DomainDecayConfig(
        volatility=DomainVolatility.SEMI_VOLATILE,
        max_age_hours=168,  # 7 giorni
        decay_rate=0.02,
        preserve_patterns=True,
        tool_first=False,
    ),
    "science_research": DomainDecayConfig(
        volatility=DomainVolatility.SEMI_VOLATILE,
        max_age_hours=4320,  # 6 mesi
        decay_rate=0.001,
        preserve_patterns=True,
        tool_first=False,
    ),
    # Stable: decay molto lento
    "knowledge_media": DomainDecayConfig(
        volatility=DomainVolatility.STABLE,
        max_age_hours=8760,  # 1 anno
        decay_rate=0.0005,
        preserve_patterns=True,
        tool_first=False,
    ),
    "medical": DomainDecayConfig(
        volatility=DomainVolatility.STABLE,
        max_age_hours=17520,  # 2 anni
        decay_rate=0.0001,
        preserve_patterns=True,
        tool_first=False,
    ),
    "utility": DomainDecayConfig(
        volatility=DomainVolatility.STABLE,
        max_age_hours=None,  # No limit
        decay_rate=0.0,
        preserve_patterns=False,
        tool_first=True,  # IP lookup, random, etc.
    ),
    # Permanent: mai scade
    "user_preferences": DomainDecayConfig(
        volatility=DomainVolatility.PERMANENT,
        max_age_hours=None,
        decay_rate=0.0,
        preserve_patterns=True,
        tool_first=False,
    ),
}

# Configurazione default per domini non specificati
DEFAULT_DECAY_CONFIG = DomainDecayConfig(
    volatility=DomainVolatility.SEMI_VOLATILE,
    max_age_hours=720,  # 30 giorni
    decay_rate=0.01,
    preserve_patterns=True,
    tool_first=False,
)


def get_decay_config(domain: str) -> DomainDecayConfig:
    """Ottiene configurazione decay per un dominio.

    Args:
        domain: Nome dominio (es. 'sports_nba')

    Returns:
        Configurazione decay, default se dominio non configurato
    """
    return DOMAIN_DECAY_CONFIGS.get(domain, DEFAULT_DECAY_CONFIG)


def calculate_decay_score(
    base_score: float,
    event_time: datetime,
    domain: str,
    now: datetime | None = None,
) -> float:
    """Calcola score con time-decay domain-aware.

    Formula: score * exp(-decay_rate * (age / max_age))

    Args:
        base_score: Score originale dalla ricerca vettoriale
        event_time: Timestamp dell'episodio
        domain: Nome dominio per lookup config
        now: Timestamp corrente (default: utcnow)

    Returns:
        Score modificato con decay temporale

    Example:
        >>> calculate_decay_score(0.9, datetime(2024, 1, 1), "sports_nba")
        0.45  # Decay aggressivo, partita vecchia
        >>> calculate_decay_score(0.9, datetime(2024, 1, 1), "medical")
        0.89  # Decay lento, dati medici stabili
    """
    if now is None:
        now = datetime.now(UTC)

    config = get_decay_config(domain)

    # Permanent: no decay
    if config.volatility == DomainVolatility.PERMANENT:
        return base_score

    # No max_age: decay lineare basato su rate
    if config.max_age_hours is None:
        return base_score

    # Calcola età in ore
    age_hours = (now - event_time).total_seconds() / 3600

    # Se oltre max_age, score = 0
    if age_hours > config.max_age_hours:
        return 0.0

    # Decay esponenziale normalizzato
    normalized_age = age_hours / config.max_age_hours
    decay_factor = math.exp(-config.decay_rate * normalized_age * 10)

    return base_score * decay_factor


def is_data_expired(
    event_time: datetime,
    domain: str,
    now: datetime | None = None,
) -> bool:
    """Verifica se un episodio è scaduto (oltre max_age).

    Args:
        event_time: Timestamp episodio
        domain: Nome dominio
        now: Timestamp corrente

    Returns:
        True se l'episodio dovrebbe essere eliminato
    """
    if now is None:
        now = datetime.now(UTC)

    config = get_decay_config(domain)

    if config.max_age_hours is None:
        return False

    age_hours = (now - event_time).total_seconds() / 3600
    return age_hours > config.max_age_hours


def should_use_tool_first(domain: str) -> bool:
    """Determina se il dominio richiede tool-first approach.

    Per domini volatili, SEMPRE chiamare tool per dati freschi
    prima di consultare memoria.

    Args:
        domain: Nome dominio

    Returns:
        True se deve chiamare tool prima di memoria
    """
    config = get_decay_config(domain)
    return config.tool_first


def get_cleanup_cutoff(domain: str, now: datetime | None = None) -> datetime | None:
    """Calcola cutoff datetime per cleanup episodi scaduti.

    Args:
        domain: Nome dominio
        now: Timestamp corrente

    Returns:
        Datetime prima del quale eliminare episodi, None se no cleanup
    """
    if now is None:
        now = datetime.now(UTC)

    config = get_decay_config(domain)

    if config.max_age_hours is None:
        return None

    return now - timedelta(hours=config.max_age_hours)


class DecayStats(BaseModel):
    """Statistiche decay per monitoring."""

    domain: str
    episodes_checked: int = 0
    episodes_expired: int = 0
    patterns_extracted: int = 0
    avg_decay_factor: float = 1.0


async def cleanup_expired_episodes(
    domain: str,
    delete_fn: Any,  # Callable per eliminazione
    extract_pattern_fn: Any | None = None,  # Callable per estrazione pattern
    now: datetime | None = None,
) -> DecayStats:
    """Cleanup episodi scaduti per un dominio.

    Usato da Sleep Mode per garbage collection notturna.

    Args:
        domain: Nome dominio da pulire
        delete_fn: Funzione async per eliminare episodi
        extract_pattern_fn: Funzione async per estrarre pattern (opzionale)
        now: Timestamp corrente

    Returns:
        Statistiche cleanup
    """
    if now is None:
        now = datetime.now(UTC)

    config = get_decay_config(domain)
    stats = DecayStats(domain=domain)

    cutoff = get_cleanup_cutoff(domain, now)
    if cutoff is None:
        logger.debug("no_cleanup_needed", domain=domain)
        return stats

    logger.info(
        "starting_cleanup",
        domain=domain,
        cutoff=cutoff.isoformat(),
        preserve_patterns=config.preserve_patterns,
    )

    # TODO: Implementare quando integrato con EpisodicMemory
    # 1. Query episodi oltre cutoff
    # 2. Se preserve_patterns, estrai pattern prima di eliminare
    # 3. Elimina episodi
    # 4. Aggiorna statistiche

    return stats
