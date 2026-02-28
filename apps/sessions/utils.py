"""
Session and authentication utilities.

Provides:
- Common utilities for IP extraction, device detection
- Session creation helper

Note: JWT access token issuance is handled by ``apps.authn.services.jwt.JWTService``.
Use ``AuthenticationService.authenticate_with_password()`` (and related methods) for
full login flows that create a session, issue a JWT, and return an
``AuthenticationResult``.
"""

from datetime import timedelta


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def create_user_session(user, request):
    """Create a new AuthSession for a user (cookie/session-cookie flows).

    For API flows that need JWT tokens, use ``AuthenticationService`` directly.
    """
    from apps.sessions.enums import SessionChannel
    from apps.sessions.models import AuthSession

    ip_address = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
    device_type = detect_device_type(user_agent)

    # user IS the Principal (AUTH_USER_MODEL = accounts.Principal)
    principal = user

    session, _cookie_handle_raw, _refresh_token_raw = AuthSession.objects.create_session(
        principal=principal,
        channel=SessionChannel.API,
        ip_address=ip_address or "0.0.0.0",
        user_agent=user_agent,
        absolute_ttl=timedelta(days=30),
        metadata={"device_type": device_type},
    )
    return session


def detect_device_type(user_agent):
    """Detect device type from user agent string."""
    user_agent_lower = user_agent.lower()
    if any(x in user_agent_lower for x in ["mobile", "android", "iphone", "ipad"]):
        if "tablet" in user_agent_lower or "ipad" in user_agent_lower:
            return "tablet"
        return "mobile"
    return "desktop"
