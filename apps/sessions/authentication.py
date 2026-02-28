"""
Authentication classes supporting both JWT and cookie-based auth.

Provides two independent authentication strategies:

``SessionJWTAuthentication``
    Validates JWT access tokens issued by ``JWTService`` (our own, not simplejwt).
    Reads from the ``Authorization: Bearer <token>`` header.
    Also checks the ``access_token`` cookie as fallback.
    On success, returns ``(principal, session)`` where ``session`` is a
    live ``AuthSession`` row.

``SessionAuthentication``
    Cookie-based authentication using our ``AuthSession`` model.
    Looks up the session via the ``user_session_id`` stored in the
    Django session cookie.

``DualAuthentication``
    Tries ``SessionJWTAuthentication`` first, falls back to
    ``SessionAuthentication``.  Registered as the default in
    ``FORGE_AUTHENTICATION_CLASSES``.
"""

from __future__ import annotations

import logging

from apps.authn.exceptions import TokenExpiredError, TokenInvalidError
from apps.authn.services.jwt import JWTService
from apps.core.api import exceptions
from apps.core.api.authentication import BaseAuthentication
from apps.sessions.models import AuthSession

logger = logging.getLogger(__name__)


class SessionJWTAuthentication(BaseAuthentication):
    """
    JWT authentication backed by ``AuthSession``.

    Every access token carries a ``sid`` (session UUID).  On each request the
    session is loaded from the database and validated with ``session.is_valid``,
    providing immediate revocation when a session is disabled or the principal's
    security stamp is bumped.

    Token sources (checked in order):
    1. ``Authorization: Bearer <token>`` header
    2. ``access_token`` cookie (cookie-based SPA flows)
    """

    keyword = "Bearer"

    def authenticate(self, request):
        raw_token = self._get_raw_token(request)
        if raw_token is None:
            return None  # Let the next backend try

        try:
            principal, session = JWTService.authenticate(raw_token)
        except (TokenExpiredError, TokenInvalidError) as exc:
            raise exceptions.AuthenticationFailed(str(exc)) from exc
        except exceptions.AuthenticationFailed:
            raise

        # Attach session for middleware convenience
        request.auth_session = session
        return principal, session

    def authenticate_header(self, request) -> str:
        return 'Bearer realm="api"'

    def _get_raw_token(self, request) -> str | None:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith(f"{self.keyword} "):
            return auth_header[len(self.keyword) + 1 :].strip() or None

        # Cookie fallback
        return request.COOKIES.get("access_token") or None


class SessionAuthentication(BaseAuthentication):
    """
    Cookie-based session authentication using the ``AuthSession`` model.

    Reads ``user_session_id`` from the Django session / cookie store and
    returns the associated ``(principal, session)`` pair.
    """

    def authenticate(self, request):
        if not hasattr(request, "session"):
            return None

        user_session_id = request.session.get("user_session_id")
        if not user_session_id:
            return None

        try:
            session = AuthSession.objects.select_related("principal").get(
                pk=user_session_id,
                deleted_at__isnull=True,
                disabled_at__isnull=True,
            )
        except AuthSession.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Session not found") from exc

        if not session.is_valid:
            raise exceptions.AuthenticationFailed("Session is not valid")

        request.auth_session = session
        principal = session.principal
        return principal, session


class DualAuthentication(BaseAuthentication):
    """
    Composite authentication: JWT token first, then cookie session.

    Order:
    1. ``SessionJWTAuthentication`` (``Authorization`` header or cookie)
    2. ``SessionAuthentication``   (Django session cookie)
    """

    def __init__(self):
        self.jwt_auth = SessionJWTAuthentication()
        self.session_auth = SessionAuthentication()

    def authenticate(self, request):
        result = self.jwt_auth.authenticate(request)
        if result is not None:
            return result

        return self.session_auth.authenticate(request)

    def authenticate_header(self, request) -> str:
        return self.jwt_auth.authenticate_header(request)
