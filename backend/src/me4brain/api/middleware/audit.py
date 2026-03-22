"""Audit Logging Middleware.

Structured audit logging per GDPR/HIPAA compliance.
Registra tutti gli accessi alle API con informazioni dettagliate.
"""

import time
from typing import Any
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = structlog.get_logger("audit")


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Middleware per audit logging strutturato."""

    # Endpoints da non loggare (health checks, metrics)
    SKIP_PATHS = {"/health", "/health/live", "/health/ready", "/metrics"}

    # Campi sensibili da mascherare
    SENSITIVE_FIELDS = {"password", "token", "api_key", "secret", "authorization"}

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Intercetta e logga ogni richiesta."""
        # Skip health checks
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Genera request ID
        request_id = str(uuid4())
        start_time = time.time()

        # Estrai info dalla richiesta
        audit_context = self._extract_audit_context(request, request_id)

        # Log richiesta in ingresso
        logger.info(
            "api_request",
            **audit_context,
            event_type="request_start",
        )

        # Esegui richiesta
        response: Response | None = None
        error: Exception | None = None

        try:
            response = await call_next(request)
        except Exception as e:
            error = e
            raise
        finally:
            # Calcola durata
            duration_ms = (time.time() - start_time) * 1000

            # Log richiesta completata
            self._log_response(
                audit_context=audit_context,
                response=response,
                error=error,
                duration_ms=duration_ms,
            )

        return response

    def _extract_audit_context(
        self,
        request: Request,
        request_id: str,
    ) -> dict[str, Any]:
        """Estrae contesto per audit log."""
        # Headers rilevanti (mascherati se sensibili)
        headers = {}
        for key, value in request.headers.items():
            key_lower = key.lower()
            if any(s in key_lower for s in self.SENSITIVE_FIELDS):
                headers[key] = "[REDACTED]"
            elif key_lower in {"user-agent", "x-tenant-id", "x-request-id", "x-forwarded-for"}:
                headers[key] = value

        # Client IP
        client_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        return {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": str(request.query_params) if request.query_params else None,
            "client_ip": client_ip,
            "user_agent": request.headers.get("user-agent", ""),
            "tenant_id": request.headers.get("x-tenant-id", "default"),
            "headers": headers,
        }

    def _log_response(
        self,
        audit_context: dict[str, Any],
        response: Response | None,
        error: Exception | None,
        duration_ms: float,
    ) -> None:
        """Logga risposta della richiesta."""
        log_data = {
            **audit_context,
            "event_type": "request_complete",
            "duration_ms": round(duration_ms, 2),
        }

        if response:
            log_data["status_code"] = response.status_code
            log_data["success"] = 200 <= response.status_code < 400

        if error:
            log_data["error"] = str(error)[:500]
            log_data["error_type"] = type(error).__name__
            log_data["success"] = False

        # Usa livello appropriato
        if error or (response and response.status_code >= 500):
            logger.error("api_response", **log_data)
        elif response and response.status_code >= 400:
            logger.warning("api_response", **log_data)
        else:
            logger.info("api_response", **log_data)


class AuditEvent:
    """Helper per loggare eventi di audit specifici."""

    @staticmethod
    def user_action(
        action: str,
        tenant_id: str,
        user_id: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Logga un'azione utente."""
        logger.info(
            "user_action",
            action=action,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            event_type="user_action",
        )

    @staticmethod
    def data_access(
        operation: str,
        tenant_id: str,
        user_id: str,
        data_type: str,
        record_count: int = 1,
        fields_accessed: list[str] | None = None,
    ) -> None:
        """Logga accesso a dati (GDPR read/export)."""
        logger.info(
            "data_access",
            operation=operation,
            tenant_id=tenant_id,
            user_id=user_id,
            data_type=data_type,
            record_count=record_count,
            fields_accessed=fields_accessed or [],
            event_type="data_access",
        )

    @staticmethod
    def data_modification(
        operation: str,
        tenant_id: str,
        user_id: str,
        data_type: str,
        record_id: str,
        changes: dict[str, Any] | None = None,
    ) -> None:
        """Logga modifica dati."""
        logger.info(
            "data_modification",
            operation=operation,
            tenant_id=tenant_id,
            user_id=user_id,
            data_type=data_type,
            record_id=record_id,
            changes=changes or {},
            event_type="data_modification",
        )

    @staticmethod
    def security_event(
        event_type: str,
        severity: str,  # "info", "warning", "critical"
        details: dict[str, Any],
        client_ip: str | None = None,
    ) -> None:
        """Logga evento di sicurezza."""
        log_func = {
            "info": logger.info,
            "warning": logger.warning,
            "critical": logger.error,
        }.get(severity, logger.info)

        log_func(
            "security_event",
            security_event_type=event_type,
            severity=severity,
            details=details,
            client_ip=client_ip,
            event_type="security",
        )

    @staticmethod
    def gdpr_request(
        request_type: str,  # "access", "rectification", "erasure", "portability"
        tenant_id: str,
        user_id: str,
        status: str,  # "received", "processing", "completed", "rejected"
        details: dict[str, Any] | None = None,
    ) -> None:
        """Logga richieste GDPR."""
        logger.info(
            "gdpr_request",
            request_type=request_type,
            tenant_id=tenant_id,
            user_id=user_id,
            status=status,
            details=details or {},
            event_type="gdpr",
        )
