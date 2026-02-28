"""
Authentication audit logging.

Direct audit helpers used by authn services.  Replaces the signal → handler
indirection that previously coupled services to an implicit event bus.

Usage::

    from apps.authn.audit import authn_audit

    authn_audit(event_type="LOGIN_SUCCESS", principal=principal, request=request, auth_method="password")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


def authn_audit(
    *,
    event_type: str,
    principal: Any = None,
    request: HttpRequest | None = None,
    **details: Any,
) -> None:
    """
    Record an authentication audit event.

    Falls back to structured logging when AuditLog is unavailable (e.g. tests).

    Args:
        event_type: An uppercase identifier string (e.g. "LOGIN_SUCCESS").
        principal: Principal responsible for the event (optional).
        request: HTTP request associated with the event (optional).
        **details: Additional event-specific fields passed through to AuditLog.
    """
    try:
        from apps.accounts.models.audit import AuditLog

        AuditLog.log(principal=principal, event_type=event_type, request=request, **details)
    except Exception:
        logger.info(
            "AUDIT: event=%s principal=%s details=%s",
            event_type,
            getattr(principal, "pk", None),
            details,
        )
