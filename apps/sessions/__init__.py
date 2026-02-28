"""
Sessions app.

Session platform (multi-principal, risk, device posture, lifecycle):
- AuthSession and (later) ServiceSession, DeviceSession, etc.
- Refresh token rotation state (if stored)
- Device fingerprinting, trusted devices
- Session risk scoring & anomaly flags
- Revocation/logouts, cleanup jobs
- Session events (optional audit table)

Depends on: core (and only references principals via settings.AUTH_USER_MODEL)
Important: sessions should not import authn or authz. It's a platform layer.
"""

default_app_config = "apps.sessions.apps.SessionsConfig"
