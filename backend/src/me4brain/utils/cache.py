"""Cache Decorator - Decorator per caching risposte in Redis."""

import hashlib
import json
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, ParamSpec

import structlog

logger = structlog.get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def cached(
    ttl: int = 900,
    key_prefix: str = "cache",
    exclude_args: Optional[list[str]] = None,
):
    """
    Decorator per cache responses in Redis.

    Args:
        ttl: Time-to-live in secondi (default: 15 minuti)
        key_prefix: Prefisso per la chiave cache
        exclude_args: Argomenti da escludere dalla chiave (es. session_id)

    Usage:
        @cached(ttl=900, key_prefix="weather")
        async def get_weather(city: str) -> dict:
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Lazy import per evitare circular imports
            from me4brain.core.cache.manager import get_cache_manager

            cache_manager = get_cache_manager()
            if cache_manager is None:
                # Cache non disponibile, esegui direttamente
                return await func(*args, **kwargs)

            # Genera cache key
            cache_key = _generate_cache_key(
                key_prefix, func.__name__, args, kwargs, exclude_args
            )

            # Prova a recuperare dalla cache
            cached_value = await cache_manager.get(cache_key)
            if cached_value is not None:
                logger.debug("cache_hit", key=cache_key)
                return cached_value

            # Cache miss: esegui funzione
            logger.debug("cache_miss", key=cache_key)
            result = await func(*args, **kwargs)

            # Salva in cache
            await cache_manager.set(cache_key, result, ttl=ttl)

            return result

        return wrapper

    return decorator


def _generate_cache_key(
    prefix: str,
    func_name: str,
    args: tuple,
    kwargs: dict,
    exclude_args: Optional[list[str]] = None,
) -> str:
    """Genera chiave cache unica."""
    exclude = exclude_args or []

    # Filtra kwargs escludendo argomenti specificati
    filtered_kwargs = {k: v for k, v in kwargs.items() if k not in exclude}

    # Serializza args e kwargs
    try:
        key_data = json.dumps(
            {"args": args, "kwargs": filtered_kwargs},
            sort_keys=True,
            default=str,
        )
    except (TypeError, ValueError):
        # Fallback per oggetti non serializzabili
        key_data = f"{args}:{filtered_kwargs}"

    # Hash per chiave più compatta
    key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]

    return f"{prefix}:{func_name}:{key_hash}"


def invalidate_cache(key_prefix: str) -> Callable:
    """
    Decorator per invalidare cache dopo l'esecuzione.

    Usage:
        @invalidate_cache("weather")
        async def update_weather_config(...):
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            result = await func(*args, **kwargs)

            # Invalida cache
            from me4brain.core.cache.manager import get_cache_manager

            cache_manager = get_cache_manager()
            if cache_manager:
                count = await cache_manager.invalidate(key_prefix)
                logger.info("cache_invalidated", prefix=key_prefix, count=count)

            return result

        return wrapper

    return decorator
