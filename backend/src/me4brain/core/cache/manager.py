"""Cache Manager - Gestione cache centralizzata con TTL per domain."""

import json
from typing import Any, Optional

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class CacheStats:
    """Statistiche cache."""

    def __init__(
        self,
        hits: int = 0,
        misses: int = 0,
        keys_count: int = 0,
        memory_bytes: int = 0,
    ):
        self.hits = hits
        self.misses = misses
        self.keys_count = keys_count
        self.memory_bytes = memory_bytes

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class CacheManager:
    """
    Gestione cache centralizzata.

    Fornisce:
    - TTL configurabili per domain
    - Invalidazione per pattern
    - Statistiche hit/miss
    """

    # TTL di default per domain (secondi)
    DEFAULT_TTLS: dict[str, int] = {
        "web_search": 900,  # 15 min
        "geo_weather": 1800,  # 30 min
        "finance_crypto": 300,  # 5 min
        "entertainment": 3600,  # 1 ora
        "knowledge_media": 1800,  # 30 min
        "sports_nba": 300,  # 5 min (live scores)
        "travel": 3600,  # 1 ora
        "jobs": 7200,  # 2 ore
        "default": 600,  # 10 min fallback
    }

    # Namespace per chiavi
    KEY_PREFIX = "me4brain:cache"

    def __init__(self, redis: Redis, key_prefix: Optional[str] = None):
        """
        Inizializza il cache manager.

        Args:
            redis: Client Redis async
            key_prefix: Prefisso chiavi (default: me4brain:cache)
        """
        self.redis = redis
        self.prefix = key_prefix or self.KEY_PREFIX

        # Contatori locali (per stats veloci)
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[Any]:
        """
        Recupera valore dalla cache.

        Args:
            key: Chiave cache

        Returns:
            Valore deserializzato o None se non trovato
        """
        full_key = f"{self.prefix}:{key}"

        try:
            value = await self.redis.get(full_key)
            if value is not None:
                self._hits += 1
                return json.loads(value)
            else:
                self._misses += 1
                return None
        except Exception as e:
            logger.warning("cache_get_error", key=key, error=str(e))
            self._misses += 1
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        domain: Optional[str] = None,
    ) -> bool:
        """
        Salva valore in cache.

        Args:
            key: Chiave cache
            value: Valore da salvare (deve essere JSON serializzabile)
            ttl: TTL in secondi (override domain default)
            domain: Nome domain per TTL automatico

        Returns:
            True se salvato, False altrimenti
        """
        full_key = f"{self.prefix}:{key}"

        # Determina TTL
        if ttl is None:
            ttl = self.DEFAULT_TTLS.get(
                domain or "default", self.DEFAULT_TTLS["default"]
            )

        try:
            serialized = json.dumps(value, default=str)
            await self.redis.setex(full_key, ttl, serialized)
            logger.debug("cache_set", key=key, ttl=ttl)
            return True
        except Exception as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Elimina singola chiave."""
        full_key = f"{self.prefix}:{key}"
        try:
            count = await self.redis.delete(full_key)
            return count > 0
        except Exception as e:
            logger.warning("cache_delete_error", key=key, error=str(e))
            return False

    async def invalidate(self, pattern: str) -> int:
        """
        Invalida tutte le chiavi che matchano il pattern.

        Args:
            pattern: Pattern glob (es. "weather:*")

        Returns:
            Numero di chiavi invalidate
        """
        full_pattern = f"{self.prefix}:{pattern}:*"

        try:
            # Usa SCAN per evitare blocchi su DB grandi
            count = 0
            cursor = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor, match=full_pattern, count=100
                )

                if keys:
                    count += await self.redis.delete(*keys)

                if cursor == 0:
                    break

            logger.info("cache_invalidated", pattern=pattern, count=count)
            return count

        except Exception as e:
            logger.error("cache_invalidate_error", pattern=pattern, error=str(e))
            return 0

    async def invalidate_all(self) -> int:
        """Invalida TUTTA la cache (attenzione!)."""
        return await self.invalidate("*")

    async def get_stats(self) -> CacheStats:
        """
        Ottiene statistiche cache.

        Returns:
            CacheStats con hit/miss rate e info memoria
        """
        try:
            # Conta chiavi
            full_pattern = f"{self.prefix}:*"
            keys_count = 0
            cursor = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor, match=full_pattern, count=100
                )
                keys_count += len(keys)
                if cursor == 0:
                    break

            # Info memoria (approssimativa)
            info = await self.redis.info("memory")
            memory = info.get("used_memory", 0)

            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                keys_count=keys_count,
                memory_bytes=memory,
            )

        except Exception as e:
            logger.warning("cache_stats_error", error=str(e))
            return CacheStats(hits=self._hits, misses=self._misses)

    def get_ttl_for_domain(self, domain: str) -> int:
        """Ottiene TTL configurato per un domain."""
        return self.DEFAULT_TTLS.get(domain, self.DEFAULT_TTLS["default"])

    def set_ttl_for_domain(self, domain: str, ttl: int) -> None:
        """Imposta TTL custom per un domain."""
        self.DEFAULT_TTLS[domain] = ttl


# Singleton globale
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> Optional[CacheManager]:
    """Ottiene il cache manager globale."""
    return _cache_manager


def set_cache_manager(manager: CacheManager) -> None:
    """Imposta il cache manager globale."""
    global _cache_manager
    _cache_manager = manager


async def initialize_cache_manager(
    redis_url: str = "redis://localhost:6379",
) -> CacheManager:
    """
    Inizializza e configura il cache manager.

    Args:
        redis_url: URL connessione Redis

    Returns:
        CacheManager inizializzato
    """
    redis = Redis.from_url(redis_url, decode_responses=True)
    manager = CacheManager(redis)
    set_cache_manager(manager)
    logger.info("cache_manager_initialized", redis_url=redis_url)
    return manager
