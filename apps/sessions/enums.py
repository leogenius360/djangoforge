"""
Session-related enums.

Design
------
Sessions use CoreStatus from apps.core.enums for lifecycle state management.
Additional session-specific enums:
- SessionChannel: broad classification for session clients (stored in metadata).
- SessionCredentialKind: what kind of credential is stored in SessionCredential.

These enums are intentionally small and realistic.
"""

from __future__ import annotations

from django.db import models


class SessionChannel(models.TextChoices):
    """High-level client channel for a session."""

    BROWSER = "browser", "Browser"
    API = "api", "API"
    SERVICE = "service", "Service"
    AGENT = "agent", "Agent"


class SessionCredentialKind(models.TextChoices):
    """
    Credential types for sessions.

    SESSION_HANDLE:
        Cookie-style session handle (server-side session lookup).
    REFRESH_TOKEN:
        Refresh-token style credential for issuing new access tokens.
    ACCESS_JTI:
        Optional access token identifier for deny-list / introspection.
    """

    SESSION_HANDLE = "session_handle", "Session Handle"
    REFRESH_TOKEN = "refresh_token", "Refresh Token"
    ACCESS_JTI = "access_jti", "Access Token JTI"
    DPOP_KEY = "dpop_key", "DPoP Key"
    MTLS_CERT = "mtls_cert", "mTLS Cert"
