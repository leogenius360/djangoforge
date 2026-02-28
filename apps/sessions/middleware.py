"""
Session management middleware.

Provides session tracking and management for both cookie-based
and token-based authentication flows.
"""

import logging

from django.contrib.auth import get_user_model
from django.utils.deprecation import MiddlewareMixin

from apps.sessions.models import AuthSession

logger = logging.getLogger(__name__)
User = get_user_model()


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class SessionTrackingMiddleware(MiddlewareMixin):
    """
    Middleware to track and update session activity.

    Works alongside both cookie-based sessions and JWT token authentication.
    Updates last_activity_at for valid sessions.
    """

    def process_request(self, request):
        """Track session activity on request."""
        # Skip for unauthenticated requests
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return None

        # Try to get session from request
        session = self._get_session(request)
        if session and session.is_valid:
            # Update activity tracking (non-blocking)
            try:
                session.touch_activity(
                    ip_address=get_client_ip(request),
                    path=request.path,
                )
            except Exception as e:
                logger.warning(f"Failed to update session activity: {e}")

        # Attach session to request for easy access
        request.user_session = session
        return None

    def _get_session(self, request):
        """Get AuthSession from request."""
        # First try to get from JWT token metadata (if using token auth)
        if hasattr(request, "auth") and request.auth:
            # Auth is an AuthSession when using SessionJWTAuthentication
            # or SessionAuthentication.  Check for session_id attribute.
            session_id = None
            if hasattr(request.auth, "pk"):
                # request.auth IS the AuthSession
                return request.auth
            if hasattr(request.auth, "get"):
                session_id = request.auth.get("session_id")

            if session_id:
                try:
                    return AuthSession.objects.for_principal(request.user).get(
                        pk=session_id,
                        deleted_at__isnull=True,
                        disabled_at__isnull=True,
                    )
                except AuthSession.DoesNotExist:
                    pass

        # Try to get from cookie session
        session_id = request.session.get("user_session_id")
        if session_id:
            try:
                return AuthSession.objects.for_principal(request.user).get(
                    pk=session_id,
                    deleted_at__isnull=True,
                    disabled_at__isnull=True,
                )
            except AuthSession.DoesNotExist:
                pass

        # Try to get from header (X-Session-ID)
        session_id = request.META.get("HTTP_X_SESSION_ID")
        if session_id:
            try:
                return AuthSession.objects.for_principal(request.user).get(
                    pk=session_id,
                    deleted_at__isnull=True,
                    disabled_at__isnull=True,
                )
            except AuthSession.DoesNotExist:
                pass

        # Fall back to most recent active session
        return (
            AuthSession.objects.for_principal(request.user)
            .filter(deleted_at__isnull=True, disabled_at__isnull=True)
            .order_by("-last_seen_at")
            .first()
        )
