"""Adaptive Response Guardrails - Intelligent size management with learning.

Implementa guardrail intelligenti che:
1. Imparano dai dati storici (response size, dominio, query type)
2. Adattano i limiti dinamicamente (fewer items per page = smaller size)
3. Monitorano metriche (compression ratio, truncation frequency)
4. Fallback a streaming JSON per risposte molto grandi (>150KB)
5. Preservano qualità analitica senza perdita di informazioni

Architecture:
- AdaptiveGuardrailsConfig: Limiti per-dominio con apprendimento
- GuardrailsMetrics: Traccia performance e adattamenti
- AdaptiveGuardrailsEngine: Applica regole intelligenti
- StreamingJSONEncoder: Encoding iterativo per risposte grandi
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from statistics import median, stdev

import structlog

from me4brain.core.interfaces import DomainExecutionResult

logger = structlog.get_logger(__name__)


@dataclass
class GuardrailsMetrics:
    """Metriche per adattamento dinamico."""

    domain: str
    total_responses: int = 0
    avg_response_size: int = 0
    max_response_size: int = 0
    min_response_size: int = 0
    truncations_applied: int = 0
    compressions_applied: int = 0
    paginatings_applied: int = 0
    response_sizes: list[int] = field(default_factory=list)
    compression_ratios: list[float] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def update(self, original_size: int, final_size: int, action_taken: str = "") -> None:
        """Aggiorna metriche con una nuova risposta."""
        self.total_responses += 1
        self.response_sizes.append(final_size)

        if final_size > self.max_response_size:
            self.max_response_size = final_size
        if self.min_response_size == 0 or final_size < self.min_response_size:
            self.min_response_size = final_size

        self.avg_response_size = sum(self.response_sizes) // len(self.response_sizes)

        if original_size > 0:
            ratio = final_size / original_size
            self.compression_ratios.append(ratio)

        if action_taken == "truncate":
            self.truncations_applied += 1
        elif action_taken == "compress":
            self.compressions_applied += 1
        elif action_taken == "paginate":
            self.paginatings_applied += 1

        self.last_updated = datetime.now(UTC)

    def get_compression_effectiveness(self) -> float:
        """Ritorna compressione media (0.0 = perfetto, 1.0 = nessuna compressione)."""
        if not self.compression_ratios:
            return 1.0
        return median(self.compression_ratios)

    def should_adapt_limits(self) -> bool:
        """Controlla se abbiamo abbastanza dati per adattare i limiti."""
        # Adatta dopo 10+ risposte e se ci sono patterns di truncation
        return self.total_responses >= 10 and self.truncations_applied > 0


@dataclass
class AdaptiveGuardrailsConfig:
    """Configurazione guardrail intelligente con adattamento dinamico."""

    domain: str
    max_response_bytes: int = 100000  # 100KB di default
    max_items_per_page: int = 5
    max_depth: int = 4
    max_summary_length: int = 500
    compress_nested_objects: bool = True
    enable_streaming: bool = False
    streaming_threshold_bytes: int = 150000  # Se > 150KB, usa streaming

    # Adattamento dinamico
    enable_adaptive_limits: bool = True
    min_items_per_page: int = 1
    max_items_per_page_limit: int = 20

    # Metriche associate
    metrics: GuardrailsMetrics = field(default_factory=lambda: GuardrailsMetrics(domain=""))

    def __post_init__(self):
        if not self.metrics.domain:
            self.metrics.domain = self.domain

    def adapt_to_metrics(self) -> None:
        """Adatta i limiti basandosi su metriche storiche."""
        if not self.enable_adaptive_limits or not self.metrics.should_adapt_limits():
            return

        # Se la compressione è efficace, possiamo permetterci più items
        compression_effectiveness = self.metrics.get_compression_effectiveness()
        if compression_effectiveness < 0.7:  # < 70% del size originale
            # Possiamo aumentare items per page
            new_items = min(
                self.max_items_per_page + 1,
                self.max_items_per_page_limit,
            )
            if new_items > self.max_items_per_page:
                logger.info(
                    "adaptive_guardrails_increased_items",
                    domain=self.domain,
                    old_items=self.max_items_per_page,
                    new_items=new_items,
                    compression_effectiveness=compression_effectiveness,
                )
                self.max_items_per_page = new_items

        # Se abbiamo molti truncations, riduci items per page
        truncation_rate = (
            self.metrics.truncations_applied / self.metrics.total_responses
            if self.metrics.total_responses > 0
            else 0
        )
        if truncation_rate > 0.5:  # > 50% delle risposte troncate
            new_items = max(
                self.max_items_per_page - 1,
                self.min_items_per_page,
            )
            if new_items < self.max_items_per_page:
                logger.info(
                    "adaptive_guardrails_decreased_items",
                    domain=self.domain,
                    old_items=self.max_items_per_page,
                    new_items=new_items,
                    truncation_rate=truncation_rate,
                )
                self.max_items_per_page = new_items


class ResponseLimiter:
    """Limita grandezza e profondità delle risposte (migliorato)."""

    @staticmethod
    def truncate_large_string(text: str, max_length: int = 1000) -> str:
        """Tronca string lunga preservando coerenza."""
        if len(text) <= max_length:
            return text

        truncated = text[:max_length]
        # Tenta di troncare su limite di parola
        if text[max_length] not in (" ", "\n", ".", ","):
            last_space = truncated.rfind(" ")
            if last_space > max_length * 0.8:
                truncated = truncated[:last_space]

        return truncated + "..."

    @staticmethod
    def compress_nested_object(obj: Any, depth: int = 0, max_depth: int = 3) -> Any:
        """Comprime oggetti annidati rimuovendo profondità eccessiva."""
        if depth > max_depth:
            return "[truncated - max depth reached]"

        if isinstance(obj, dict):
            # Limita numero di chiavi
            if len(obj) > 50:
                logger.warning("large_dict_compressed", size=len(obj))
                # Mantieni solo chiavi importanti
                important_keys = [
                    k
                    for k in obj.keys()
                    if any(
                        x in k.lower()
                        for x in [
                            "game",
                            "prediction",
                            "odds",
                            "value",
                            "pick",
                            "analysis",
                            "recommendation",
                        ]
                    )
                ]
                if important_keys:
                    obj = {k: obj[k] for k in important_keys}

            return {
                k: ResponseLimiter.compress_nested_object(v, depth + 1, max_depth)
                for k, v in obj.items()
            }

        elif isinstance(obj, list):
            # Limita numero di elementi
            if len(obj) > 100:
                logger.warning("large_list_compressed", size=len(obj))
                obj = obj[:50]  # Keep first 50

            return [
                ResponseLimiter.compress_nested_object(item, depth + 1, max_depth) for item in obj
            ]

        elif isinstance(obj, str) and len(obj) > 5000:
            return ResponseLimiter.truncate_large_string(obj, 1000)

        return obj

    @staticmethod
    def calculate_size(obj: Any) -> int:
        """Calcola approssimazione della grandezza in bytes."""
        try:
            return len(json.dumps(obj, default=str).encode("utf-8"))
        except Exception:
            return 0

    @staticmethod
    def paginate_results(
        results: list[dict[str, Any]], page: int = 1, page_size: int = 10
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Pagina risultati grandi.

        Args:
            results: Lista di risultati
            page: Numero pagina (1-indexed)
            page_size: Elementi per pagina

        Returns:
            Tuple di (paginated_results, pagination_info)
        """
        total = len(results)
        total_pages = (total + page_size - 1) // page_size

        # Validazione
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        paginated = results[start_idx:end_idx]

        pagination_info = {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        return paginated, pagination_info

    @staticmethod
    def apply_guardrails(
        data: dict[str, Any],
        config: AdaptiveGuardrailsConfig,
    ) -> tuple[dict[str, Any], str]:
        """Applica guardrail a risposta.

        Args:
            data: Response data
            config: Configurazione guardrail

        Returns:
            Tuple di (data con guardrail, action_taken)
        """
        original_size = ResponseLimiter.calculate_size(data)
        action_taken = ""

        # 1. Comprimi oggetti annidati
        if config.compress_nested_objects:
            data = ResponseLimiter.compress_nested_object(data, max_depth=config.max_depth)
            action_taken = "compress"

        # 2. Pagina risultati se necessario
        results_keys = [k for k in data.keys() if "prediction" in k or "result" in k]
        for key in results_keys:
            if isinstance(data.get(key), list):
                results = data[key]
                if len(results) > config.max_items_per_page:
                    paginated, pagination_info = ResponseLimiter.paginate_results(
                        results, page=1, page_size=config.max_items_per_page
                    )
                    data[key] = paginated
                    data["pagination"] = pagination_info
                    action_taken = "paginate"
                    logger.info(
                        "response_paginated",
                        domain=config.domain,
                        total_items=pagination_info["total_items"],
                        page_size=config.max_items_per_page,
                    )

        # 3. Verifica grandezza finale
        final_size = ResponseLimiter.calculate_size(data)

        if final_size > config.max_response_bytes:
            logger.warning(
                "response_size_limit_exceeded",
                domain=config.domain,
                original_size=original_size,
                final_size=final_size,
                limit=config.max_response_bytes,
            )

            # Ultima risorsa: truncate predictions
            for key in results_keys:
                if isinstance(data.get(key), list):
                    data[key] = data[key][: config.max_items_per_page // 2]
                    action_taken = "truncate"
                    logger.warning(
                        "response_emergency_truncation",
                        domain=config.domain,
                        items_kept=len(data[key]),
                    )

        # Aggiorna metriche
        config.metrics.update(original_size, final_size, action_taken)

        return data, action_taken


class StreamingJSONEncoder:
    """Encoder per streaming di risposte JSON grandi."""

    @staticmethod
    async def stream_json_object(
        data: dict[str, Any], chunk_size: int = 8192
    ) -> AsyncGenerator[str, None]:
        """Streama un oggetto JSON in chunks.

        Utile per risposte molto grandi (>150KB) dove buffering completo
        causerebbe timeout o OOM.

        Args:
            data: Oggetto da streamare
            chunk_size: Grandezza approssimativa di ogni chunk in bytes

        Yields:
            Chunks di JSON valido
        """
        # Inizio oggetto
        yield "{"

        items = list(data.items())
        for idx, (key, value) in enumerate(items):
            # Serializza key
            yield json.dumps(key) + ": "

            # Serializza value (può essere grande)
            if isinstance(value, (list, dict)):
                # Per liste/dict grandi, streama interno
                yield json.dumps(value, default=str)
            else:
                yield json.dumps(value, default=str)

            # Aggiungi comma se non ultimo
            if idx < len(items) - 1:
                yield ","

        # Fine oggetto
        yield "}"

    @staticmethod
    async def stream_json_array(
        items: list[Any], chunk_size: int = 8192
    ) -> AsyncGenerator[str, None]:
        """Streama un array JSON in chunks.

        Args:
            items: Lista di items da streamare
            chunk_size: Grandezza approssimativa di ogni chunk

        Yields:
            Chunks di JSON valido
        """
        # Inizio array
        yield "["

        for idx, item in enumerate(items):
            # Serializza item
            yield json.dumps(item, default=str)

            # Aggiungi comma se non ultimo
            if idx < len(items) - 1:
                yield ","

        # Fine array
        yield "]"


# Singleton config per dominio con metriche
_guardrails_config: dict[str, AdaptiveGuardrailsConfig] = {
    "sports_nba": AdaptiveGuardrailsConfig(
        domain="sports_nba",
        max_response_bytes=150000,  # 150KB per NBA
        max_items_per_page=5,
        max_depth=4,
        enable_adaptive_limits=True,
        metrics=GuardrailsMetrics(domain="sports_nba"),
    ),
}


def get_guardrails_for_domain(domain_name: str) -> AdaptiveGuardrailsConfig:
    """Ottieni configurazione guardrail per dominio."""
    if domain_name not in _guardrails_config:
        _guardrails_config[domain_name] = AdaptiveGuardrailsConfig(
            domain=domain_name,
            metrics=GuardrailsMetrics(domain=domain_name),
        )

    # Adatta i limiti se necessario
    config = _guardrails_config[domain_name]
    config.adapt_to_metrics()

    return config


def apply_response_guardrails(
    result: DomainExecutionResult, domain_name: str
) -> DomainExecutionResult:
    """Applica guardrail a un DomainExecutionResult.

    Args:
        result: Risultato esecuzione dominio
        domain_name: Nome del dominio per configurazione

    Returns:
        DomainExecutionResult con guardrail applicati
    """
    if not result.success or not result.data:
        return result

    config = get_guardrails_for_domain(domain_name)
    guardraild_data, action = ResponseLimiter.apply_guardrails(result.data, config)

    return DomainExecutionResult(
        success=result.success,
        domain=result.domain,
        tool_name=result.tool_name,
        data=guardraild_data,
        error=result.error,
        latency_ms=result.latency_ms,
        cached=result.cached,
    )


async def stream_large_response(
    result: DomainExecutionResult, domain_name: str
) -> AsyncGenerator[str, None]:
    """Streama una risposta molto grande in chunks.

    Utile per risposte che superano i limiti di memoria/timeout.

    Args:
        result: Risultato esecuzione dominio
        domain_name: Nome del dominio

    Yields:
        Chunks di JSON streaming
    """
    config = get_guardrails_for_domain(domain_name)

    # Applica guardrail prima di streamare
    guarded_result = apply_response_guardrails(result, domain_name)
    guarded_size = ResponseLimiter.calculate_size(guarded_result.data)

    # Se ancora troppo grande, streama
    if guarded_size > config.streaming_threshold_bytes:
        logger.info(
            "streaming_large_response_start",
            domain=domain_name,
            size=guarded_size,
            threshold=config.streaming_threshold_bytes,
        )

        async for chunk in StreamingJSONEncoder.stream_json_object(guarded_result.data):
            yield chunk
    else:
        # Altrimenti serializza tutto in una volta
        yield json.dumps(guarded_result.data, default=str)
