"""
FORGE_* settings with validation at startup.

All DjangoForge settings live under a single ``FORGE`` dict in Django settings.
Missing keys fall back to sensible defaults.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

DEFAULTS: dict[str, Any] = {
    # ── Auth / trusted-proxy ─────────────────────────────────────────
    "AUTH_HEADER_USER_ID": "HTTP_X_USER_ID",
    "AUTH_HEADER_EMAIL": "HTTP_X_EMAIL",
    "AUTH_HEADER_GROUPS": "HTTP_X_GROUPS",
    "AUTH_HEADER_TENANT": "HTTP_X_TENANT",
    "AUTH_HEADER_SCOPES": "HTTP_X_SCOPES",
    "AUTH_HEADER_PROVIDER": "HTTP_X_AUTH_PROVIDER",
    "AUTH_TRUSTED_PROXIES": [],  # list of CIDRs / IPs
    "AUTH_REQUIRE_PROXY": False,
    "AUTH_JWT_ENABLED": True,
    # ── Correlation / observability ───────────────────────────────────
    "CORRELATION_ID_HEADER": "HTTP_X_CORRELATION_ID",
    "CORRELATION_ID_GENERATE": True,
    # ── Security headers ─────────────────────────────────────────────
    "SECURITY_HEADERS_ENABLED": True,
    # ── Events / outbox ──────────────────────────────────────────────
    "EVENTS_ENABLED": True,
    "EVENTS_BROKER_BACKEND": "djangoforge.events.backends.LogBrokerBackend",
    "EVENTS_MAX_PUBLISH_BATCH": 50,
    "EVENTS_PUBLISH_TIMEOUT_SECONDS": 30,
    # ── OpenAPI / schema ─────────────────────────────────────────────
    "OPENAPI_REQUIRE_OPERATION_ID": True,
    "OPENAPI_REQUIRE_TAGS": True,
    "OPENAPI_REQUIRE_RESPONSES": True,
    "OPENAPI_REQUIRE_AUTH": True,
    # ── API versioning ───────────────────────────────────────────────
    "API_VERSION": "v1",
}


class ForgeSettings:
    """Lazy accessor for ``settings.FORGE``."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        user: dict[str, Any] = getattr(settings, "FORGE", {})
        if name in user:
            return user[name]
        if name in DEFAULTS:
            return DEFAULTS[name]
        raise AttributeError(f"Unknown FORGE setting: {name}")

    def validate(self) -> None:
        """Run startup validation. Called from ``AppConfig.ready()``."""
        user: dict[str, Any] = getattr(settings, "FORGE", {})
        for key in user:
            if key not in DEFAULTS:
                raise ImproperlyConfigured(f"Unknown FORGE setting: '{key}'")

    def as_dict(self) -> dict[str, Any]:
        """Return merged defaults + overrides."""
        merged = dict(DEFAULTS)
        merged.update(getattr(settings, "FORGE", {}))
        return merged


forge_settings = ForgeSettings()
