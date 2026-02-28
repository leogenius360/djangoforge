"""
QuerySet and Manager for audit Event models.

Immutability contract
---------------------
``EventQuerySet.update()`` and ``bulk_update()`` reject any attempt to modify
fields listed in the model's ``IMMUTABLE_FIELDS`` class variable.  Only fields
in ``MUTABLE_FIELDS`` are permitted after creation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils import timezone

from apps.auditing.exceptions import HardDeleteForbiddenError, ImmutabilityError

if TYPE_CHECKING:
    from collections.abc import Iterable


class EventQuerySet(models.QuerySet):
    """
    Custom QuerySet for audit Event models.

    Enforces immutability on update paths and implements soft-delete semantics.
    """

    # ------------------------------------------------------------------
    # Immutability enforcement
    # ------------------------------------------------------------------

    def update(self, **kwargs: Any) -> int:
        self._enforce_immutability(set(kwargs.keys()))
        return super().update(**kwargs)

    def bulk_update(self, objs: Iterable[models.Model], fields: Iterable[str], batch_size: int | None = None) -> int:
        self._enforce_immutability(set(fields))
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def _enforce_immutability(self, field_names: set[str]) -> None:
        """Raise ImmutabilityError if any field in ``field_names`` is immutable."""
        immutable = getattr(self.model, "IMMUTABLE_FIELDS", frozenset())
        mutable = getattr(self.model, "MUTABLE_FIELDS", frozenset())
        forbidden = field_names & immutable
        if forbidden:
            raise ImmutabilityError(forbidden_fields=forbidden, allowed_fields=mutable)

    # ------------------------------------------------------------------
    # Soft-delete (Events are never hard-deleted via the normal path)
    # ------------------------------------------------------------------

    def delete(self) -> tuple[int, dict[str, int]]:
        """Soft-delete: set ``deleted_at`` on all matched rows."""
        count = self.update(deleted_at=timezone.now())
        return count, {self.model._meta.label: count}

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """
        Physically delete rows.

        Intended only for GDPR purge routines.  Raises
        ``HardDeleteForbiddenError`` if invoked outside of a permitted path.
        To perform a GDPR purge, call ``queryset.hard_delete()`` in a dedicated
        data-retention management command.
        """
        import inspect

        stack = inspect.stack()
        callers = [frame.function for frame in stack[1:5]]
        if "gdpr_purge" not in callers and "retention_purge" not in callers:
            raise HardDeleteForbiddenError(self.model._meta.label)
        return super().delete()

    # ------------------------------------------------------------------
    # Filtering helpers
    # ------------------------------------------------------------------

    def with_deleted(self) -> EventQuerySet:
        """Include soft-deleted events in the queryset."""
        return self.all()

    def active(self) -> EventQuerySet:
        """Exclude soft-deleted events."""
        return self.filter(deleted_at__isnull=True)

    def for_object(self, content_type: Any, object_id: str) -> EventQuerySet:
        """Filter by audited aggregate (content_type + object_id)."""
        return self.filter(content_type=content_type, object_id=str(object_id))

    def for_actor(self, actor: Any) -> EventQuerySet:
        return self.filter(actor=actor)

    def by_event_type(self, *event_types: str) -> EventQuerySet:
        return self.filter(event_type__in=event_types)

    def created_between(self, start: Any, end: Any) -> EventQuerySet:
        return self.filter(created_at__gte=start, created_at__lte=end)

    def pending_dispatch(self) -> EventQuerySet:
        """Events with at least one backend still pending dispatch."""
        # PostgreSQL: filter where backends_pending JSON array is non-empty
        return self.exclude(backends_pending=[])

    def fully_dispatched(self) -> EventQuerySet:
        """Events fully dispatched to all configured backends."""
        return self.filter(backends_pending=[])

    def with_related(self) -> EventQuerySet:
        """Pre-fetch commonly needed related objects."""
        return self.select_related("content_type", "actor", "parent")

    def verify_integrity(self) -> dict[str, bool]:
        """
        Verify the checksum integrity of all events in the queryset.

        Returns a mapping ``{str(event_pk): bool}`` — ``True`` means verified.
        This is expensive and should only be called in maintenance scripts.
        """
        from apps.auditing.utils.integrity import IntegrityService

        svc = IntegrityService()
        results: dict[str, bool] = {}
        for event in self.iterator():
            payload = event._integrity_payload()
            ok = svc.verify_event_chain(
                payload=payload,
                current_checksum=event.checksum,
                parent_checksum=event.parent_checksum,
            )
            results[str(event.pk)] = ok
        return results


class EventManager(models.Manager):
    """
    Default manager for audit Event models.

    Returns only non-soft-deleted events from ``get_queryset()``.
    Use ``Event.objects.with_deleted()`` to include deleted records.
    """

    def get_queryset(self) -> EventQuerySet:
        return EventQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)

    def with_deleted(self) -> EventQuerySet:
        """Return a queryset that includes soft-deleted events."""
        return EventQuerySet(self.model, using=self._db)

    def pending_dispatch(self) -> EventQuerySet:
        return self.get_queryset().pending_dispatch()
