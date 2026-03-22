"""Universal Guardrails Middleware for all API responses.

Applies adaptive guardrails to every API response in the system,
regardless of domain, route, or response type.

This middleware:
1. Intercepts all JSON responses before they are sent to clients
2. Applies appropriate size management (compression, pagination, streaming)
3. Tracks metrics for each route/domain
4. Adapts limits based on observed patterns
5. Ensures no response is truncated - uses pagination instead
"""

import json
import logging
from typing import Any, Callable, Optional
from datetime import UTC, datetime

from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from me4brain.domains.adaptive_guardrails import (
    get_guardrails_for_domain,
    ResponseLimiter,
    stream_large_response,
)
from me4brain.domains.universal_guardrails import get_universal_config
from me4brain.core.interfaces import DomainExecutionResult

logger = logging.getLogger(__name__)


class UniversalGuardrailsMiddleware(BaseHTTPMiddleware):
    """Middleware che applica guardrails adattivi a TUTTE le risposte API.

    Funziona su:
    - Tutte le rotte API (domains, memory, semantic, engine, etc.)
    - Tutti i tipi di risposta (JSON, streaming, paginated)
    - Tutti i domini (NBA, finance, weather, etc.)
    - Tutti i casi di errore e edge case

    Garantisce:
    - Zero truncation: usa pagination invece di tagliare dati
    - Zero data loss: tutti i campi preservati
    - Adaptive limits: impara dai pattern di risposta
    - Per-route metrics: traccia efficienza per ogni endpoint
    - Graceful degradation: compress → paginate → emergency truncate (ultimo resort)
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Intercept all responses and apply guardrails."""
        start_time = datetime.now(UTC)

        # Get route identifier for metrics
        route_id = self._get_route_id(request)

        # Call the actual endpoint
        response = await call_next(request)

        # Only apply guardrails to JSON responses with content
        if self._should_apply_guardrails(response):
            response = await self._apply_guardrails_to_response(
                response, request, route_id, start_time
            )

        return response

    def _get_route_id(self, request: Request) -> str:
        """Extract route identifier for metrics."""
        # Use path + method as route ID
        path = request.url.path
        method = request.method

        # For domain queries, extract domain name
        if "/domains" in path and method == "POST":
            # Try to extract domain from request if available
            try:
                if hasattr(request, "_json"):
                    body = request._json
                    if isinstance(body, dict) and "domain" in body:
                        return f"domains/{body['domain']}"
            except Exception:
                pass
            return "domains/query"

        # For other routes, use path segments
        segments = path.strip("/").split("/")
        return "/".join(segments[:2]) if segments else "unknown"

    def _should_apply_guardrails(self, response: Response) -> bool:
        """Check if guardrails should be applied to this response."""
        # Skip if already a streaming response
        if isinstance(response, StreamingResponse):
            return False

        # Skip if not JSON
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return False

        # Skip if no body
        if not hasattr(response, "body") or not response.body:
            return False

        # Skip if 2xx status (we only guard successful responses with content)
        if response.status_code < 200 or response.status_code >= 300:
            # For error responses, apply minimal guardrails
            return response.status_code < 400  # Guard 2xx and 3xx only

        return True

    async def _apply_guardrails_to_response(
        self,
        response: Response,
        request: Request,
        route_id: str,
        start_time: datetime,
    ) -> Response:
        """Apply adaptive guardrails to a JSON response."""
        try:
            # Parse response body
            body_bytes = response.body
            body_text = body_bytes.decode("utf-8")

            # Parse JSON
            try:
                data = json.loads(body_text)
            except json.JSONDecodeError:
                # Not valid JSON, return as-is
                return response

            # Determine domain for guardrails (prefer explicit domain, fall back to route)
            domain = self._extract_domain(request, data)

            # Get guardrails config for this domain/route using UNIVERSAL config
            config = get_universal_config(domain)

            # Calculate original size
            original_size = len(body_bytes)

            # Apply guardrails
            guarded_data, metadata = ResponseLimiter.apply_guardrails(data, config)

            # Update metrics
            self._update_metrics(config, original_size, metadata, route_id)

            # Check if response size exceeds streaming threshold
            guarded_json = json.dumps(guarded_data)
            guarded_size = len(guarded_json.encode("utf-8"))

            if guarded_size > 150_000:  # 150KB streaming threshold
                # Return streaming response
                return await self._create_streaming_response(guarded_data, response)

            # Return regular JSON response with guardrails applied
            return JSONResponse(
                content=guarded_data,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        except Exception as e:
            self.logger.error(
                "guardrails_middleware_error",
                error=str(e),
                route=route_id,
                exc_info=True,
            )
            # On error, return original response
            return response

    def _extract_domain(self, request: Request, data: Any) -> str:
        """Extract domain from request or response data."""
        # Check path for domain
        path = request.url.path
        if "/domains" in path:
            # Check if DomainExecutionResult structure
            if isinstance(data, dict):
                if "domain" in data:
                    return data["domain"]
                if "data" in data and isinstance(data["data"], dict):
                    if "domain" in data["data"]:
                        return data["data"]["domain"]
            return "sports_nba"  # Default domain

        # For other routes, use route path
        segments = path.strip("/").split("/")
        if segments:
            # Map route to domain
            route = segments[0]
            domain_map = {
                "memory": "memory",
                "semantic": "semantic",
                "engine": "engine",
                "tools": "tools",
                "skills": "skills",
                "working": "working",
                "procedural": "procedural",
                "session_graph": "session_graph",
                "monitoring": "monitoring",
                "admin": "admin",
            }
            return domain_map.get(route, route)

        return "default"

    def _update_metrics(
        self, config: Any, original_size: int, metadata: dict, route_id: str
    ) -> None:
        """Update guardrails metrics for this response."""
        try:
            metrics = config.metrics

            # Update basic response count and size
            metrics.total_responses += 1
            metrics.total_bytes_received += original_size

            # Update based on action taken
            if metadata.get("compression_applied"):
                metrics.compressions_applied += 1
                compressed_size = metadata.get("compressed_size", original_size)
                metrics.total_bytes_compressed += compressed_size

            if metadata.get("pagination_applied"):
                metrics.paginatings_applied += 1

            if metadata.get("truncation_applied"):
                metrics.truncations_count += 1

            # Update last modified timestamp
            metrics.last_updated = datetime.now(UTC)

            # Log metrics update
            self.logger.debug(
                "metrics_updated",
                route=route_id,
                domain=config.domain,
                total_responses=metrics.total_responses,
                compression_ratio=metrics.avg_compression_ratio,
            )

        except Exception as e:
            self.logger.error(
                "metrics_update_error",
                error=str(e),
                exc_info=True,
            )

    async def _create_streaming_response(
        self, data: Any, original_response: Response
    ) -> StreamingResponse:
        """Create a streaming response for large data."""

        async def generate_json():
            """Generate JSON chunks asynchronously."""
            if isinstance(data, dict):
                yield "{"
                items = list(data.items())
                for i, (key, value) in enumerate(items):
                    yield json.dumps(key)
                    yield ":"
                    yield json.dumps(value)
                    if i < len(items) - 1:
                        yield ","
                yield "}"
            elif isinstance(data, list):
                yield "["
                for i, item in enumerate(data):
                    yield json.dumps(item)
                    if i < len(data) - 1:
                        yield ","
                yield "]"
            else:
                yield json.dumps(data)

        return StreamingResponse(
            generate_json(),
            status_code=original_response.status_code,
            headers=dict(original_response.headers),
            media_type="application/json",
        )


class DomainGuardrailsMiddleware(BaseHTTPMiddleware):
    """Specialized middleware for /domains endpoint.

    Applica guardrails con consapevolezza del dominio:
    - Estrae dominio dalla richiesta
    - Applica config specifico del dominio
    - Traccia metriche per dominio
    - Gestisce streaming per risposte grandi
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply domain-aware guardrails."""
        if request.url.path != "/domains/query":
            return await call_next(request)

        # Get response
        response = await call_next(request)

        if response.status_code != 200:
            return response

        try:
            # Parse response
            body = json.loads(response.body.decode("utf-8"))

            # Extract domain and apply guardrails
            domain = body.get("domain", "sports_nba")
            config = get_guardrails_for_domain(domain)

            guarded_data, _ = ResponseLimiter.apply_guardrails(body, config)

            # Return guarded response
            return JSONResponse(
                content=guarded_data,
                status_code=200,
                headers=dict(response.headers),
            )

        except Exception as e:
            logger.error(f"Domain guardrails error: {e}", exc_info=True)
            return response


def apply_guardrails_to_all_responses() -> None:
    """Convenience function to document middleware registration in main.py."""
    pass
