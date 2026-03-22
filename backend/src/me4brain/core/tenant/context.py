"""Tenant Context - ContextVars per propagazione tenant in async stack."""

from __future__ import annotations

import contextlib
from contextvars import ContextVar, Token
from typing import Optional, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from me4brain.core.tenant.types import TenantConfig

logger = structlog.get_logger(__name__)


# --- Exceptions ---


class TenantNotSetError(Exception):
    """Raised quando tenant_id richiesto ma non impostato nel context."""

    def __init__(self, message: str = "Tenant ID not set in context"):
        super().__init__(message)


class TenantAccessDeniedError(Exception):
    """Raised quando accesso cross-tenant tentato."""

    def __init__(self, requested: str, current: str):
        super().__init__(
            f"Access denied: requested tenant {requested}, current {current}"
        )
        self.requested = requested
        self.current = current


# --- Context Variables ---


_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="")
_tenant_config: ContextVar[Optional["TenantConfig"]] = ContextVar(
    "tenant_config", default=None
)
_user_id: ContextVar[str] = ContextVar("user_id", default="")


# --- Getters ---


def get_tenant_id() -> str:
    """
    Ottiene tenant ID corrente dal context.

    Returns:
        Tenant ID

    Raises:
        TenantNotSetError: Se tenant non impostato
    """
    tid = _tenant_id.get()
    if not tid:
        raise TenantNotSetError()
    return tid


def get_tenant_id_or_none() -> Optional[str]:
    """
    Ottiene tenant ID o None se non impostato.

    Returns:
        Tenant ID o None
    """
    tid = _tenant_id.get()
    return tid if tid else None


def get_tenant_config() -> Optional["TenantConfig"]:
    """
    Ottiene config tenant corrente.

    Returns:
        TenantConfig o None
    """
    return _tenant_config.get()


def get_user_id() -> Optional[str]:
    """
    Ottiene user ID corrente.

    Returns:
        User ID o None
    """
    uid = _user_id.get()
    return uid if uid else None


# --- Setters ---


def set_tenant(
    tenant_id: str,
    config: Optional["TenantConfig"] = None,
    user_id: Optional[str] = None,
) -> Token:
    """
    Imposta tenant nel context asincrono.

    Args:
        tenant_id: ID del tenant
        config: Configurazione tenant (opzionale)
        user_id: ID utente (opzionale)

    Returns:
        Token per reset
    """
    token = _tenant_id.set(tenant_id)

    if config:
        _tenant_config.set(config)

    if user_id:
        _user_id.set(user_id)

    logger.debug("tenant_context_set", tenant_id=tenant_id, user_id=user_id)

    return token


def reset_tenant(token: Token) -> None:
    """
    Resetta tenant context usando token.

    Args:
        token: Token da set_tenant()
    """
    _tenant_id.reset(token)
    _tenant_config.set(None)
    _user_id.set("")


# --- Context Manager ---


@contextlib.contextmanager
def tenant_context(
    tenant_id: str,
    config: Optional["TenantConfig"] = None,
    user_id: Optional[str] = None,
):
    """
    Context manager per operazioni tenant-scoped.

    Esempio:
        with tenant_context("tenant-123"):
            # Tutte le operazioni usano tenant-123
            await memory.add_message(...)

    Args:
        tenant_id: ID del tenant
        config: Configurazione tenant (opzionale)
        user_id: ID utente (opzionale)

    Yields:
        None
    """
    token = set_tenant(tenant_id, config, user_id)
    try:
        yield
    finally:
        reset_tenant(token)


# --- Validation Helpers ---


def validate_tenant_access(requested_tenant: str) -> None:
    """
    Valida che il tenant richiesto corrisponda al context.

    Args:
        requested_tenant: Tenant ID richiesto

    Raises:
        TenantAccessDeniedError: Se mismatch
    """
    current = get_tenant_id_or_none()

    if current and current != requested_tenant:
        logger.warning(
            "cross_tenant_access_denied",
            requested=requested_tenant,
            current=current,
        )
        raise TenantAccessDeniedError(requested_tenant, current)


def resolve_tenant_id(explicit_tenant: Optional[str] = None) -> str:
    """
    Risolve tenant ID: usa quello esplicito o dal context.

    Utile per backward compatibility nei memory layers.

    Args:
        explicit_tenant: Tenant ID esplicito (opzionale)

    Returns:
        Tenant ID risolto

    Raises:
        TenantNotSetError: Se nessun tenant disponibile
    """
    if explicit_tenant:
        # Valida che non ci sia conflitto con context
        current = get_tenant_id_or_none()
        if current and current != explicit_tenant:
            logger.warning(
                "tenant_mismatch",
                explicit=explicit_tenant,
                context=current,
            )
        return explicit_tenant

    return get_tenant_id()
