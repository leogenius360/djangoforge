"""
Auditing middleware for per-request context capture.

``AuditingMiddleware`` stores the current HTTP request in thread-local storage
(safe for WSGI threads) and populates the audit context variables (actor, IP,
user-agent, request ID) so that ``AuditService`` can include them in every
``Event`` created during that request.

Helper functions
----------------
:func:`get_current_request`  — retrieve the request for the active thread.
:func:`get_current_user`     — retrieve the authenticated user (or ``None``).
:func:`get_client_ip`        — extract the client IP from a request.
:func:`get_user_agent`       — extract the User-Agent header from a request.
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

# Thread-local storage for the current request.
_thread_local = threading.local()


# ---------------------------------------------------------------------------
# Helper functions (importable by other modules)
# ---------------------------------------------------------------------------


def get_current_request() -> HttpRequest | None:
    """Return the HTTP request currently executing on this thread, or ``None``."""
    return getattr(_thread_local, "request", None)


def get_current_user() -> Any:
    """
    Return the authenticated user for the current request, or ``None``.

    Returns ``None`` when there is no active request or the user is anonymous.
    """
    request = get_current_request()
    if request is None:
        return None
    user = getattr(request, "user", None)
    if user is None:
        return None
    if not getattr(user, "is_authenticated", False):
        return None
    return user


def get_client_ip(request: HttpRequest) -> str | None:
    """
    Extract the client IP address from ``request``.

    Prefers the first address in the ``X-Forwarded-For`` header (set by
    load-balancers / proxies) and falls back to ``REMOTE_ADDR``.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_user_agent(request: HttpRequest) -> str | None:
    """Extract the User-Agent header from ``request``, or ``None``."""
    return request.META.get("HTTP_USER_AGENT")


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class AuditingMiddleware:
    """
    Django middleware that captures the HTTP request context for audit logging.

    Sets the thread-local request and populates audit context variables (actor,
    session, IP, user-agent, correlation ID) at the start of each request.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.process_request(request)
        try:
            response = self.get_response(request)
        except Exception:
            # Ensure audit context does not leak across requests when an exception
            # bypasses normal response handling.
            self._clear_context()
            raise
        return self.process_response(request, response)

    def _clear_context(self) -> None:
        """Reset contextvars and clear thread-local request for this thread."""
        tokens = getattr(_thread_local, "audit_tokens", None)
        if tokens:
            for var, token in tokens.items():
                # Best-effort cleanup.
                with contextlib.suppress(Exception):
                    var.reset(token)
        _thread_local.audit_tokens = None
        _thread_local.request = None

    def process_request(self, request: HttpRequest) -> None:
        """
        Store the request on the current thread and publish audit context vars.

        Called at the start of each request (and by tests directly).
        """
        from apps.auditing.context import (
            _audit_actor,
            _audit_ip_address,
            _audit_request_id,
            _audit_session,
            _audit_user_agent,
        )

        _thread_local.request = request

        user = get_current_user()
        ip_address = get_client_ip(request)
        user_agent = get_user_agent(request)
        request_id = getattr(request, "correlation_id", None) or str(uuid.uuid4())

        session_key = None
        session = getattr(request, "session", None)
        if session is not None:
            session_key = getattr(session, "session_key", None)

        # Populate async-safe context vars as well (for ASGI / Celery consumers
        # that share this middleware's setup logic).
        # Store tokens so we can reset to the previous values on response.
        _thread_local.audit_tokens = {
            _audit_actor: _audit_actor.set(user),
            _audit_session: _audit_session.set(session_key),
            _audit_ip_address: _audit_ip_address.set(ip_address),
            _audit_user_agent: _audit_user_agent.set(user_agent),
            _audit_request_id: _audit_request_id.set(request_id),
        }

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """
        Clear the stored request from thread-local storage.

        Called at the end of each request (and by tests directly).
        """
        self._clear_context()
        return response
