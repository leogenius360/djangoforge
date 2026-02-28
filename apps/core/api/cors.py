"""
CORS middleware for the DjangoForge API layer.

Replaces ``django-cors-headers`` with a pure Django middleware that reads
configuration from ``settings.CORS_*`` variables.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse


class CorsMiddleware:
    """
    Pure Django CORS middleware.

    Reads the same settings as ``django-cors-headers``:
    - ``CORS_ALLOWED_ORIGINS``
    - ``CORS_ALLOW_CREDENTIALS``
    - ``CORS_ALLOW_HEADERS``
    - ``CORS_ALLOW_METHODS``
    - ``CORS_ALLOW_ALL_ORIGINS``
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Handle preflight requests
        if request.method == "OPTIONS":
            response = HttpResponse()
            self._add_cors_headers(request, response)
            return response

        response = self.get_response(request)
        self._add_cors_headers(request, response)
        return response

    def _add_cors_headers(self, request: HttpRequest, response: HttpResponse) -> None:
        origin = request.META.get("HTTP_ORIGIN", "")
        if not origin:
            return

        allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        allow_all = getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False)

        if not allow_all and origin not in allowed_origins:
            return

        response["Access-Control-Allow-Origin"] = origin

        if getattr(settings, "CORS_ALLOW_CREDENTIALS", False):
            response["Access-Control-Allow-Credentials"] = "true"

        # Methods
        methods = getattr(settings, "CORS_ALLOW_METHODS", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
        response["Access-Control-Allow-Methods"] = ", ".join(methods)

        # Headers
        allowed_headers = getattr(settings, "CORS_ALLOW_HEADERS", [])
        if allowed_headers:
            response["Access-Control-Allow-Headers"] = ", ".join(allowed_headers)

        response["Access-Control-Max-Age"] = "86400"
