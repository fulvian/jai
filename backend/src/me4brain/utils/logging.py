"""Me4BrAIn Logging Configuration.

Configura structlog per logging JSON strutturato con correlation ID e tenant context.
"""

import logging
import sys
from typing import Literal

import structlog
from structlog.types import Processor


def configure_logging(
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO",
) -> None:
    """Configura structlog con output JSON per produzione.

    Args:
        log_level: Livello di logging (DEBUG, INFO, WARNING, ERROR)
    """
    # Processors comuni
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Processor finale dipende da ambiente
    if sys.stderr.isatty():
        # Console colorata per sviluppo
        final_processor: Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON per produzione (cloud logging)
        final_processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configura logging stdlib
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=final_processor,
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, log_level))

    # Riduci verbosità di librerie esterne
    for logger_name in ["httpx", "httpcore", "uvicorn.access"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def bind_tenant_context(tenant_id: str, user_id: str, session_id: str) -> None:
    """Bind tenant context alle log lines.

    Chiamato dal middleware di autenticazione.

    Args:
        tenant_id: ID del tenant
        user_id: ID dell'utente
        session_id: ID della sessione
    """
    structlog.contextvars.bind_contextvars(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
    )


def clear_context() -> None:
    """Pulisce il contesto dopo la richiesta."""
    structlog.contextvars.clear_contextvars()
