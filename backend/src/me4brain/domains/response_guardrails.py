"""Response Guardrails - Control output size and quality.

Implementa guardrail per:
1. Limitare max_tokens delle risposte LLM
2. Paginare risultati grandi
3. Comprimere dati verbosi
4. Mantenere profondità analisi senza overflow
"""

import json
from typing import Any, Optional
from dataclasses import dataclass

import structlog

from me4brain.core.interfaces import DomainExecutionResult

logger = structlog.get_logger(__name__)


@dataclass
class ResponseGuardrails:
    """Configurazione guardrail per dominio."""

    max_response_bytes: int = 50000  # 50KB max
    max_items_per_page: int = 10
    max_summary_length: int = 500  # Summary chars before truncation
    compress_nested_objects: bool = True
    max_depth: int = 3  # Max nesting depth


class ResponseLimiter:
    """Limita grandezza e profondità delle risposte."""

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
                    if any(x in k.lower() for x in ["game", "prediction", "odds", "value", "pick"])
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
        guardrails: ResponseGuardrails = ResponseGuardrails(),
    ) -> dict[str, Any]:
        """Applica guardrail a risposta.

        Args:
            data: Response data
            guardrails: Configurazione guardrail

        Returns:
            Data con guardrail applicati
        """
        original_size = ResponseLimiter.calculate_size(data)

        # 1. Comprimi oggetti annidati
        if guardrails.compress_nested_objects:
            data = ResponseLimiter.compress_nested_object(data, max_depth=guardrails.max_depth)

        # 2. Pagina risultati se necessario
        if "daily_predictions" in data and isinstance(data["daily_predictions"], list):
            predictions = data["daily_predictions"]
            if len(predictions) > guardrails.max_items_per_page:
                paginated, pagination_info = ResponseLimiter.paginate_results(
                    predictions, page=1, page_size=guardrails.max_items_per_page
                )
                data["daily_predictions"] = paginated
                data["pagination"] = pagination_info
                logger.info(
                    "response_paginated",
                    total_items=pagination_info["total_items"],
                    page_size=guardrails.max_items_per_page,
                )

        # 3. Verifica grandezza finale
        final_size = ResponseLimiter.calculate_size(data)
        if final_size > guardrails.max_response_bytes:
            logger.warning(
                "response_size_limit_exceeded",
                original_size=original_size,
                final_size=final_size,
                limit=guardrails.max_response_bytes,
            )
            # Ultima risorsa: truncate predictions
            if "daily_predictions" in data:
                data["daily_predictions"] = data["daily_predictions"][
                    : guardrails.max_items_per_page // 2
                ]
                logger.warning(
                    "response_emergency_truncation", items_kept=len(data["daily_predictions"])
                )

        return data


# Singleton config per dominio
_guardrails_config: dict[str, ResponseGuardrails] = {
    "sports_nba": ResponseGuardrails(
        max_response_bytes=100000,  # 100KB per NBA (molto dati)
        max_items_per_page=5,  # Ma pagina a 5 giochi per chunk
        max_depth=4,
    ),
}


def get_guardrails_for_domain(domain_name: str) -> ResponseGuardrails:
    """Ottieni configurazione guardrail per dominio."""
    return _guardrails_config.get(domain_name, ResponseGuardrails())


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

    guardrails = get_guardrails_for_domain(domain_name)
    guardraild_data = ResponseLimiter.apply_guardrails(result.data, guardrails)

    return DomainExecutionResult(
        success=result.success,
        domain=result.domain,
        tool_name=result.tool_name,
        data=guardraild_data,
        error=result.error,
        latency_ms=result.latency_ms,
        cached=result.cached,
    )
