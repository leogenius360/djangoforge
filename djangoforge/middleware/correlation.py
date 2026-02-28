"""
Correlation-ID middleware.

Reads ``X-Correlation-Id`` from the incoming request (or generates one) and
attaches it to the response and to a thread-local / context-var so structured
logging and tracing can include it automatically.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING

from djangoforge.settings import forge_settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

_correlation_id: ContextVar[str] = ContextVar("forge_correlation_id", default="")


def get_correlation_id() -> str:
    """Return the current correlation ID (empty string if unset)."""
    return _correlation_id.get()


class CorrelationIdMiddleware:
    """Inject / propagate a correlation ID on every request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        header = forge_settings.CORRELATION_ID_HEADER
        cid = request.META.get(header, "")
        if not cid and forge_settings.CORRELATION_ID_GENERATE:
            cid = uuid.uuid4().hex
        token = _correlation_id.set(cid)
        try:
            response = self.get_response(request)
            response["X-Correlation-Id"] = cid
            return response
        finally:
            _correlation_id.reset(token)
