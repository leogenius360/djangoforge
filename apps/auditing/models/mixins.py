"""
AuditableManagerMixin and AuditableQuerySetMixin for automatic bulk-operation auditing.

Drop-in Manager replacement for Django models that should participate in
automatic audit logging (including bulk creates/updates/deletes).

Usage::

    class MyModel(models.Model):
        name = models.CharField(max_length=100)

        objects = AuditableManagerMixin()

Alternatively, use :class:`~apps.auditing.mixins.AuditableModelMixin` which
includes this manager automatically.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import models, transaction

from apps.auditing.registry import audit_registry
from apps.auditing.services import create_audit_entry, serialize_model_state

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AuditableModelMixin
# ---------------------------------------------------------------------------


class AuditableModelMixin(models.Model):
    """
    Abstract mixin that opts a model into the auditing subsystem.

    Self-registers with :data:`~apps.auditing.registry.audit_registry` when
    the concrete subclass is defined.  Subclasses can customise behaviour by
    defining an inner ``class Audit`` with any of the following attributes:

    Attributes
    ----------
    track_fields:
        Whitelist of field names to include in snapshots.
        ``None`` / empty list = include all non-excluded fields.
    exclude_fields:
        Field names to always exclude (merged with ``GLOBAL_EXCLUDE_FIELDS``).
    snapshot_on_create:
        Store a full snapshot for CREATE events (default: global setting).
    snapshot_on_delete:
        Store a full snapshot for DELETE events (default: global setting).
    snapshot_interval:
        Store a full snapshot every N events; delta-only between snapshots.
    """

    class Audit:
        """Default audit configuration.  Override in concrete subclasses."""

        track_fields: list[str] | None = None
        exclude_fields: list[str] | None = None
        snapshot_on_create: bool | None = None
        snapshot_on_delete: bool | None = None
        snapshot_interval: int | None = None

    class Meta:
        abstract = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Only register non-abstract concrete models.
        meta = getattr(cls, "_meta", None)
        if meta is None or meta.abstract:
            return

        # Read configuration from the inner Audit class.
        audit_cfg = cls.__dict__.get("Audit") or getattr(cls, "Audit", None)
        track_fields: list[str] | None = getattr(audit_cfg, "track_fields", None)
        exclude_fields: list[str] | None = getattr(audit_cfg, "exclude_fields", None)
        snapshot_on_create: bool | None = getattr(audit_cfg, "snapshot_on_create", None)
        snapshot_on_delete: bool | None = getattr(audit_cfg, "snapshot_on_delete", None)
        snapshot_interval: int | None = getattr(audit_cfg, "snapshot_interval", None)

        try:
            from apps.auditing.registry import audit_registry

            audit_registry.register(
                cls,
                track_fields=list(track_fields) if track_fields else None,
                exclude_fields=list(exclude_fields) if exclude_fields else None,
                snapshot_on_create=snapshot_on_create,
                snapshot_on_delete=snapshot_on_delete,
                snapshot_interval=snapshot_interval,
            )
        except Exception:
            # Registration can fail during early app loading; the AppConfig.ready()
            # hook will retry via AUDITED_APPS / AUDITED_MODELS settings.
            import logging

            logging.getLogger(__name__).debug(
                "AuditableModelMixin: deferred registration for %s (app registry not ready).",
                cls.__qualname__,
            )

    # ------------------------------------------------------------------
    # save() — creates CREATE or UPDATE audit event inside atomic block
    # ------------------------------------------------------------------

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Any = None,
    ) -> None:
        """
        Save the model and create an audit event in the same transaction.

        For new instances, a CREATE event is written.  For existing instances,
        the pre-save state is fetched from the database and an UPDATE event
        records what changed.

        When auditing is disabled or the model is not registered, falls back to
        the standard ``super().save()`` call without any overhead.
        """
        if not audit_registry.should_audit_model(self.__class__):
            super().save(
                force_insert=force_insert,
                force_update=force_update,
                using=using,
                update_fields=update_fields,
            )
            return

        is_insert = not bool(self.pk) or self._state.adding or force_insert
        db_alias = using or self._state.db

        pre_state: dict[str, Any] | None = None
        if not is_insert and self.pk is not None:
            try:
                old_obj = self.__class__._default_manager.using(db_alias).get(pk=self.pk)
            except self.__class__.DoesNotExist:
                pre_state = None
            else:
                pre_state = serialize_model_state(old_obj)

        with transaction.atomic(using=db_alias):
            super().save(
                force_insert=force_insert,
                force_update=force_update,
                using=using,
                update_fields=update_fields,
            )
            self._audit("create" if is_insert else "update", pre_state=pre_state)

    # ------------------------------------------------------------------
    # delete() — creates DELETE audit event inside atomic block
    # ------------------------------------------------------------------

    def delete(
        self,
        using: str | None = None,
        keep_parents: bool = False,
    ) -> tuple[int, dict[str, int]]:
        """
        Delete the model instance and create a DELETE audit event in the same transaction.

        When auditing is disabled or the model is not registered, falls back to
        the standard ``super().delete()`` call without any overhead.
        """
        if not audit_registry.should_audit_model(self.__class__):
            return super().delete(using=using, keep_parents=keep_parents)

        db_alias = using or self._state.db
        with transaction.atomic(using=db_alias):
            # For DELETE events we must capture state *before* the row is removed.
            self._audit("delete")
            return super().delete(using=using, keep_parents=keep_parents)

    def _audit(
        self,
        event_type: str,
        *,
        pre_state: dict[str, Any] | None = None,
        actor: Any = None,
        comment: str = "",
    ) -> None:
        """Helper to create an audit entry for this instance."""
        if not audit_registry.should_audit_model(self.__class__):
            return

        comment = comment or (
            f"{event_type.upper()} event for {self.__class__.__name__} instance pk={getattr(self, 'pk', '?')}"
        )

        try:
            state = serialize_model_state(self)
            create_audit_entry(self, event_type, state, actor=actor, pre_state=pre_state, comment=comment)
        except Exception as exc:
            logger.warning(
                "AuditableModelMixin: failed to create audit entry for %s pk=%s: %s",
                self.__class__.__name__,
                getattr(self, "pk", "?"),
                exc,
            )
            raise


class AuditableQuerySetMixin(models.QuerySet):
    """
    QuerySet that creates audit events for bulk operations.

    Overrides ``bulk_create``, ``bulk_update``, and ``update`` to emit
    ``BULK_CREATE``, ``BULK_UPDATE``, and ``BULK_UPDATE`` events respectively.

    Note: The ``delete()`` method emits ``BULK_DELETE`` events.
    """

    def create(self, **kwargs):
        """Create with auditing.

        Note: if the model also uses ``AuditableModelMixin``, the instance-level
        ``save()`` will already have created an audit event -- skip the queryset-
        level audit to avoid duplicates.
        """
        with transaction.atomic(using=self.db):
            instance = super().create(**kwargs)
            if not isinstance(instance, AuditableModelMixin):
                self._audit_bulk([instance], "create")
        return instance

    def update(self, **kwargs: Any) -> int:
        # Materialize PKs before the update so we can audit the right rows
        # even if the update changes the filter criteria.
        pks = list(self.values_list("pk", flat=True))
        with transaction.atomic(using=self.db):
            count = super().update(**kwargs)
            if pks:
                instances = list(self.model._default_manager.filter(pk__in=pks))
                self._audit_bulk(instances, "bulk_update")
        return count

    def delete(self) -> tuple[int, dict[str, int]]:
        # Materialize the rows before deletion so we can capture state.
        instances = list(self)
        with transaction.atomic(using=self.db):
            self._audit_bulk(instances, "bulk_delete")
            result = super().delete()
        return result

    def bulk_create(
        self,
        objs: list[models.Model],
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: list[str] | None = None,
        unique_fields: list[str] | None = None,
    ) -> list[models.Model]:
        created: list[models.Model] = []
        with transaction.atomic(using=self.db):
            created = super().bulk_create(
                objs,
                batch_size=batch_size,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )
            self._audit_bulk(created, "bulk_create")
        return created

    def bulk_update(
        self,
        objs: list[models.Model],
        fields: list[str],
        batch_size: int | None = None,
    ) -> int:
        count = 0
        with transaction.atomic(using=self.db):
            count = super().bulk_update(objs, fields, batch_size=batch_size)
            self._audit_bulk(objs, "bulk_update")
        return count

    def _audit_bulk(self, instances: list[models.Model], event_type: str) -> None:
        """Create audit events for a list of model instances."""
        if not instances:
            return

        if not audit_registry.should_audit_model(self.model):
            return

        comment = f"Bulk {event_type} of {len(instances)} instance(s) of {self.model.__name__}"
        for instance in instances:
            try:
                state = serialize_model_state(instance)
                create_audit_entry(instance, event_type, state, comment=comment)
            except Exception as exc:
                logger.warning(
                    "AuditableQuerySetMixin: failed to create audit entry for %s pk=%s: %s",
                    self.model.__name__,
                    getattr(instance, "pk", "?"),
                    exc,
                )
                raise exc


class AuditableManagerMixin(models.Manager):
    """
    Manager that returns :class:`AuditableQuerySetMixin` for automatic bulk-operation auditing.
    """

    def get_queryset(self) -> AuditableQuerySetMixin:
        return AuditableQuerySetMixin(self.model, using=self._db)
