"""
Security-headers middleware.

Adds recommended security headers to every response when
``FORGE["SECURITY_HEADERS_ENABLED"]`` is ``True``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from djangoforge.settings import forge_settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

#: Default headers applied to every response.
DEFAULT_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "X-XSS-Protection": "1; mode=block",
}


class SecurityHeadersMiddleware:
    """Append security headers to every HTTP response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if forge_settings.SECURITY_HEADERS_ENABLED:
            for name, value in DEFAULT_HEADERS.items():
                response.setdefault(name, value)
        return response
