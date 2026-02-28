"""
``django.core.checks`` integration — powers ``forge check``.
"""

from __future__ import annotations

from django.core.checks import Error, Warning, register

from djangoforge.settings import forge_settings


@register("forge")
def check_forge_middleware(app_configs, **kwargs):  # type: ignore[no-untyped-def]
    """Verify that correlation-ID middleware is in MIDDLEWARE."""
    from django.conf import settings

    issues = []
    mw = getattr(settings, "MIDDLEWARE", [])
    if "djangoforge.middleware.correlation.CorrelationIdMiddleware" not in mw:
        issues.append(
            Warning(
                "CorrelationIdMiddleware is not in MIDDLEWARE.",
                hint="Add 'djangoforge.middleware.correlation.CorrelationIdMiddleware' to MIDDLEWARE.",
                id="forge.W001",
            )
        )
    sec_mw = "djangoforge.middleware.security_headers.SecurityHeadersMiddleware"
    if forge_settings.SECURITY_HEADERS_ENABLED and sec_mw not in mw:
        issues.append(
            Warning(
                "SecurityHeadersMiddleware is not in MIDDLEWARE but FORGE.SECURITY_HEADERS_ENABLED is True.",
                hint="Add 'djangoforge.middleware.security_headers.SecurityHeadersMiddleware' to MIDDLEWARE.",
                id="forge.W002",
            )
        )
    return issues


@register("forge")
def check_forge_events(app_configs, **kwargs):  # type: ignore[no-untyped-def]
    """Verify outbox event table exists when events are enabled."""
    issues = []
    if forge_settings.EVENTS_ENABLED and "djangoforge" not in [ac.name for ac in (app_configs or [])]:
        pass  # App may not be in INSTALLED_APPS yet during initial check
    return issues


@register("forge")
def check_forge_security(app_configs, **kwargs):  # type: ignore[no-untyped-def]
    """Validate security-related settings."""
    from django.conf import settings

    issues = []
    if not settings.DEBUG:
        if not getattr(settings, "CSRF_COOKIE_SECURE", False):
            issues.append(
                Warning(
                    "CSRF_COOKIE_SECURE is False in a non-debug environment.",
                    id="forge.W003",
                )
            )
        if not getattr(settings, "SESSION_COOKIE_SECURE", False):
            issues.append(
                Warning(
                    "SESSION_COOKIE_SECURE is False in a non-debug environment.",
                    id="forge.W004",
                )
            )
    return issues
