"""
Async-safe audit context storage using Python contextvars.

Safer than thread-locals for both WSGI (threads) and ASGI (coroutines).
The ``AuditingMiddleware`` sets these vars per-request; ``AuditService``
reads them when composing an Event record.

Usage from non-request code (e.g. management commands, Celery tasks)::

    from apps.auditing.context import set_audit_context

    with set_audit_context(actor=user, request_id="job-123"):
        # All audit events created here capture actor and request_id
        MyModel.objects.create(...)
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator


# ---------------------------------------------------------------------------
# Context variables
# ---------------------------------------------------------------------------

_audit_actor: ContextVar[Any] = ContextVar("audit_actor", default=None)
_audit_session: ContextVar[Any] = ContextVar("audit_session", default=None)
_audit_request_id: ContextVar[str | None] = ContextVar("audit_request_id", default=None)
_audit_ip_address: ContextVar[str | None] = ContextVar("audit_ip_address", default=None)
_audit_user_agent: ContextVar[str | None] = ContextVar("audit_user_agent", default=None)


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------


def get_current_actor() -> Any:
    """Return the currently authenticated actor, or ``None``."""
    return _audit_actor.get()


def get_current_session() -> Any:
    """Return the current session object, or ``None``."""
    return _audit_session.get()


def get_current_request_id() -> str | None:
    """Return the current request/correlation ID, or ``None``."""
    return _audit_request_id.get()


def get_current_ip_address() -> str | None:
    """Return the client IP address for the current request, or ``None``."""
    return _audit_ip_address.get()


def get_current_user_agent() -> str | None:
    """Return the User-Agent header for the current request, or ``None``."""
    return _audit_user_agent.get()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@contextmanager
def set_audit_context(
    *,
    actor: Any = None,
    session: Any = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Iterator[None]:
    """
    Set all audit context variables for the duration of the block.

    Resets each variable to its prior value on exit, making this safe
    for nested use and re-entrant calls.

    Example::

        with set_audit_context(actor=user, ip_address="1.2.3.4"):
            instance.save()
    """
    tokens = (
        _audit_actor.set(actor),
        _audit_session.set(session),
        _audit_request_id.set(request_id),
        _audit_ip_address.set(ip_address),
        _audit_user_agent.set(user_agent),
    )
    vars_ = (_audit_actor, _audit_session, _audit_request_id, _audit_ip_address, _audit_user_agent)
    try:
        yield
    finally:
        for var, token in zip(vars_, tokens, strict=True):
            var.reset(token)
