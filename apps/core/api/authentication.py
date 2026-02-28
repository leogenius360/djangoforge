"""
Authentication base classes for the DjangoForge API layer.

Replaces ``rest_framework.authentication.BaseAuthentication`` with a pure
Django equivalent that the ``ForgeAPIView`` consults on each request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


class BaseAuthentication:
    """
    Base class for authentication.

    Subclasses must implement ``authenticate()`` and return a
    ``(user, auth_info)`` tuple on success, or ``None`` to skip.
    """

    def authenticate(self, request: HttpRequest) -> tuple | None:
        """
        Authenticate the request and return a ``(user, auth)`` tuple,
        or ``None`` if authentication was not attempted.

        Raise ``apps.core.api.exceptions.AuthenticationFailed`` on failure.
        """
        raise NotImplementedError

    def authenticate_header(self, request: HttpRequest) -> str | None:
        """
        Return a string to be used as the ``WWW-Authenticate`` header value
        in a ``401`` response, or ``None``.
        """
        return None
