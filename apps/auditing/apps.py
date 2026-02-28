"""
Django AppConfig for the auditing subsystem.
"""

from __future__ import annotations

from django.apps import AppConfig


class AuditingConfig(AppConfig):
    """Django application configuration for the auditing subsystem."""

    name = "apps.auditing"
    label = "auditing"
    verbose_name = "Auditing"

    def ready(self) -> None:
        """
        Perform startup initialization:

        1. Apply per-model settings from ``AUDITING["AUDITED_MODELS"]``.
        2. Auto-register models from ``AUDITING["AUDITED_APPS"]``.

        Audit event creation is handled by ``AuditableModelMixin.save()`` /
        ``AuditableModelMixin.delete()`` rather than Django signals.
        """
        from apps.auditing.registry import audit_registry
        from apps.auditing.settings import audit_settings

        if not audit_settings.ENABLED:
            return

        # Apply explicit per-model configuration first (higher precedence).
        if audit_settings.AUDITED_MODELS:
            audit_registry.apply_model_settings(audit_settings.AUDITED_MODELS)

        # Auto-register models from configured apps (lower precedence).
        if audit_settings.AUDITED_APPS:
            audit_registry.discover_apps(audit_settings.AUDITED_APPS)
