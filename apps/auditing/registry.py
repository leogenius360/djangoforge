"""
Audit model registry.

Maintains a mapping of audited model classes to their per-model configuration.
Provides helpers for discovery (from AUDITED_APPS) and for checking whether a
model should be audited.

The global ``audit_registry`` singleton is imported by ``AuditableModelMixin``
(which calls ``register()`` at class-definition time) and by ``apps.py.ready()``
(which performs bulk discovery from settings).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from django.db import models

logger = logging.getLogger(__name__)


@dataclass
class AuditModelConfig:
    """Per-model audit configuration.

    Fields with value ``None`` fall back to the corresponding global
    ``AuditingSettings`` setting at runtime.
    """

    model_class: type[models.Model]

    # When False the model is excluded from all auditing
    enabled: bool = True

    # Whitelist of field names to track.  Empty set = track all fields.
    track_fields: set[str] = field(default_factory=set)

    # Field names to exclude (merged with GLOBAL_EXCLUDE_FIELDS at runtime)
    exclude_fields: set[str] = field(default_factory=set)

    # Snapshot strategy overrides (None → use AuditingSettings global)
    snapshot_on_create: bool | None = None
    snapshot_on_delete: bool | None = None
    snapshot_interval: int | None = None

    @property
    def model_label(self) -> str:
        """Dotted ``app_label.model_name`` string, e.g. ``"accounts.useraccount"``."""
        return f"{self.model_class._meta.app_label}.{self.model_class._meta.model_name}"

    def should_track_field(
        self,
        field_name: str,
        global_exclude: list[str] | set[str] | None = None,
    ) -> bool:
        """Return True if ``field_name`` should be included in serialisation."""
        all_exclude = set(self.exclude_fields) | set(global_exclude or [])
        if field_name in all_exclude:
            return False
        if not self.track_fields:
            return True
        return field_name in self.track_fields

    def effective_snapshot_on_create(self, default: bool) -> bool:
        return self.snapshot_on_create if self.snapshot_on_create is not None else default

    def effective_snapshot_on_delete(self, default: bool) -> bool:
        return self.snapshot_on_delete if self.snapshot_on_delete is not None else default

    def effective_snapshot_interval(self, default: int) -> int:
        return self.snapshot_interval if self.snapshot_interval is not None else default


class AuditRegistry:
    """
    Central registry of auditable models.

    Thread-safe for read-heavy workloads (models are registered at startup).
    """

    def __init__(self) -> None:
        self._registry: dict[type[models.Model], AuditModelConfig] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        model_class: type[models.Model],
        *,
        enabled: bool | None = None,
        track_fields: set[str] | list[str] | None = None,
        exclude_fields: set[str] | list[str] | None = None,
        snapshot_on_create: bool | None = None,
        snapshot_on_delete: bool | None = None,
        snapshot_interval: int | None = None,
    ) -> AuditModelConfig:
        """
        Register ``model_class`` for auditing, or update its config.

        If the model is already registered, only the *explicitly supplied*
        keyword arguments override the existing configuration; everything else
        is preserved.  This honours the precedence order:

        1. Explicit ``audit_registry.register(Model, ...)`` call (highest)
        2. Model's inner ``class Audit:``
        3. Per-model entry in ``AUDITING["AUDITED_MODELS"]``
        4. ``AUDITING["AUDITED_APPS"]`` (global defaults / lowest)
        """
        existing = self._registry.get(model_class)

        resolved_enabled = True if enabled is None else enabled

        if existing is None:
            config = AuditModelConfig(
                model_class=model_class,
                enabled=resolved_enabled,
                track_fields=set(track_fields) if track_fields is not None else set(),
                exclude_fields=set(exclude_fields) if exclude_fields is not None else set(),
                snapshot_on_create=snapshot_on_create,
                snapshot_on_delete=snapshot_on_delete,
                snapshot_interval=snapshot_interval,
            )
        else:
            # Merge — only override what was explicitly supplied.
            config = AuditModelConfig(
                model_class=model_class,
                enabled=existing.enabled if enabled is None else enabled,
                track_fields=set(track_fields) if track_fields is not None else existing.track_fields,
                exclude_fields=set(exclude_fields) if exclude_fields is not None else existing.exclude_fields,
                snapshot_on_create=snapshot_on_create
                if snapshot_on_create is not None
                else existing.snapshot_on_create,
                snapshot_on_delete=snapshot_on_delete
                if snapshot_on_delete is not None
                else existing.snapshot_on_delete,
                snapshot_interval=snapshot_interval if snapshot_interval is not None else existing.snapshot_interval,
            )

        self._registry[model_class] = config
        logger.debug("AUDITING: registered model %r with config: %r", config.model_label, config)
        return config

    def unregister(self, model_class: type[models.Model]) -> None:
        """Remove a model from the registry."""
        self._registry.pop(model_class, None)

    def clear(self) -> None:
        """Remove all models from the registry."""
        self._registry.clear()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_apps(self, app_labels: list[str]) -> None:
        """
        Auto-register all non-abstract models in the named Django apps.

        Called from ``AuditingConfig.ready()`` based on ``AUDITING["AUDITED_APPS"]``.
        Models excluded via ``AUDITING["EXCLUDED_MODELS"]`` are skipped.
        Already-registered models are not overwritten with bare defaults.
        """
        from django.apps import apps as django_apps

        from apps.auditing.settings import audit_settings

        excluded = set(audit_settings.EXCLUDED_MODELS)

        for app_label in app_labels:
            try:
                app_config = django_apps.get_app_config(app_label)
            except LookupError:
                logger.warning("AUDITING.AUDITED_APPS: app %r not found — skipping.", app_label)
                continue

            for model_class in app_config.get_models():
                if model_class._meta.abstract:
                    continue
                label = f"{model_class._meta.app_label}.{model_class._meta.model_name}"
                if label in excluded:
                    logger.debug("AUDITING: skipping excluded model %r.", label)
                    continue

                if model_class not in self._registry:
                    # Register with bare defaults (inner Audit class may already be registered)
                    self.register(model_class)
                    logger.debug("AUDITING: auto-registered %r from AUDITED_APPS.", label)

    def apply_model_settings(self, models_config: dict[str, Any]) -> None:
        """
        Apply per-model config from ``AUDITING["AUDITED_MODELS"]``.

        Called from ``AuditingConfig.ready()``.  Entries here take lower
        precedence than an explicit programmatic ``register()`` call but
        higher than ``AUDITED_APPS`` defaults.

        ``models_config`` format::

            {
                "accounts.UserAccount": {
                    "track_fields": ["email", "status"],
                    "exclude_fields": [],
                    "snapshot_interval": 5,
                }
            }
        """
        from django.apps import apps as django_apps

        for model_label, config_dict in models_config.items():
            try:
                app_label, model_name = model_label.split(".", 1)
                model_class = django_apps.get_model(app_label, model_name)
            except (ValueError, LookupError):
                logger.warning("AUDITING.AUDITED_MODELS: model %r not found — skipping.", model_label)
                continue

            kwargs: dict[str, Any] = {}
            for key in (
                "enabled",
                "track_fields",
                "exclude_fields",
                "snapshot_on_create",
                "snapshot_on_delete",
                "snapshot_interval",
            ):
                if key in config_dict:
                    kwargs[key] = config_dict[key]

            self.register(model_class, **kwargs)

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def is_registered(self, model_class: type[models.Model]) -> bool:
        return model_class in self._registry

    def is_enabled(self, model_class: type[models.Model]) -> bool:
        config = self._registry.get(model_class)
        return config is not None and config.enabled

    def get_config(self, model_class: type[models.Model]) -> AuditModelConfig | None:
        return self._registry.get(model_class)

    def should_audit_model(self, model_class: type[models.Model]) -> bool:
        """Return True if the model is registered and auditing is globally enabled."""
        from apps.auditing.settings import audit_settings

        if not audit_settings.ENABLED:
            return False
        return self.is_enabled(model_class)

    def all_models(self) -> list[type[models.Model]]:
        """Alias for ``get_all_registered_models``."""
        return self.get_all_registered_models()

    def get_all_registered_models(self) -> list[type[models.Model]]:
        """Return all registered model classes."""
        return list(self._registry.keys())

    def get_enabled_models(self) -> list[type[models.Model]]:
        """Return model classes that are registered and enabled."""
        return [m for m, cfg in self._registry.items() if cfg.enabled]

    def get_model_labels(self) -> list[str]:
        """Return dotted ``app_label.model_name`` strings for all registered models."""
        return [cfg.model_label for cfg in self._registry.values()]

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, model_class: object) -> bool:
        return model_class in self._registry

    def __repr__(self) -> str:
        count = len(self._registry)
        return f"<AuditRegistry {count} models registered>"


# Global singleton
audit_registry: Final[AuditRegistry] = AuditRegistry()
