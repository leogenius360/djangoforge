"""Project-level QuerySet implementation.

Django bulk operations (QuerySet.update / QuerySet.bulk_update / QuerySet.delete)
bypass model.save() and therefore bypass:
- `auto_now=True` updates (updated_at)
- any model-level version bump logic (optimistic versioning)
- signals (by design)

BaseQuerySet enforces consistency for bulk operations:
- Bulk .update() sets updated_at (if present) and bumps version (if present)
- Bulk .delete() soft-deletes by default (sets deleted_at if present)
- Bulk .restore() undeletes by clearing deleted_at
- Bulk .hard_delete() physically deletes

These are intentionally small and composable mixins:
- SoftDeleteQuerySetMixin: active/deleted/soft-delete/restore semantics
- BulkConsistencyQuerySetMixin: updated_at/version enforcement for bulk updates

If you define model-specific querysets, subclass BaseQuerySet to keep these behaviors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from django.db.models import F, QuerySet
from django.utils import timezone

from apps.auditing.context import get_current_actor
from apps.core.typing import DjangoDeleteReturn, QuerySetMixinBase
from apps.core.utils.models import model_has_field

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from django.db.models import Model
else:
    Model = Any  # type: ignore[assignment]
    Iterable = Any  # type: ignore[assignment]
    Sequence = Any  # type: ignore[assignment]


class SoftDeleteQuerySetMixin(QuerySetMixinBase):
    """Active/deleted filtering plus soft-delete/restore semantics."""

    model: type[Model]

    def active(self) -> Self:
        """Return only active (non-deleted) rows (or all rows if model has no `deleted_at` and `is_active` fields)."""
        qs = self
        if self._has_model_field("is_active"):
            qs = qs.filter(is_active=True)
        if self._has_model_field("deleted_at"):
            qs = qs.filter(deleted_at__isnull=True)
        return qs

    def deleted(self) -> Self:
        """Return only soft-deleted rows (or `.none()` if model has no `deleted_at`)."""
        if not self._has_model_field("deleted_at"):
            return self.none()
        return self.filter(deleted_at__isnull=False)

    def delete(self, using: str | None = None, keep_parents: bool = False) -> DjangoDeleteReturn:
        """Soft-delete by default (Django-compatible delete return value)."""
        return self.soft_delete(using=using, keep_parents=keep_parents)

    def soft_delete(self, using: str | None = None, keep_parents: bool = False) -> DjangoDeleteReturn:
        """Bulk soft-delete rows by setting `deleted_at` (or hard-delete if unsupported).

        Also sets ``status=DELETED`` when the model has a ``status`` field,
        maintaining lifecycle coherence.
        """
        if not self._has_model_field("deleted_at"):
            return super().delete(using=using, keep_parents=keep_parents)

        qs = self.using(using) if using is not None else self
        update_kwargs: dict[str, Any] = {"deleted_at": timezone.now()}
        if self._has_model_field("deleted_by"):
            actor = get_current_actor()
            update_kwargs["deleted_by"] = actor
        count = qs.update(**update_kwargs)
        return count, {self.model._meta.label: count}

    def restore(self) -> int:
        """Bulk undelete rows by clearing `deleted_at` (returns rows updated).

        Also sets ``status=ACTIVE`` when the model has a ``status`` field.
        """
        if not self._has_model_field("deleted_at"):
            return 0
        update_kwargs: dict[str, Any] = {"deleted_at": None}
        if self._has_model_field("deleted_by"):
            update_kwargs["deleted_by"] = None
        return self.update(**update_kwargs)

    def hard_delete(self) -> DjangoDeleteReturn:
        """Physically delete rows in bulk (Django-compatible delete return value)."""
        return super().delete()

    def _has_model_field(self, name: str) -> bool:
        """Check if `name` is a Django-managed field/relation on this model."""
        if hasattr(self.model, "_field_cache"):
            if name in self.model._field_cache:
                return self.model._field_cache[name]
            self.model._field_cache = {}

        val = model_has_field(self.model, name)
        self.model._field_cache[name] = val
        return val


class BulkConsistencyQuerySetMixin(QuerySetMixinBase):
    """Enforce updated_at/version semantics for Django bulk operations."""

    def update(self, **kwargs: Any) -> int:
        """Bulk update with enforced updated_at/version semantics (returns rows updated)."""
        now = timezone.now()

        if self._has_model_field("updated_at") and "updated_at" not in kwargs:
            kwargs["updated_at"] = now
        if self._has_model_field("updated_by") and "updated_by" not in kwargs:
            kwargs["updated_by"] = get_current_actor()

        if self._has_model_field("version") and "version" not in kwargs:
            kwargs["version"] = F("version") + 1

        return super().update(**kwargs)

    def bulk_update(
        self,
        objs: Iterable[Model],
        fields: Sequence[str],
        batch_size: int | None = None,
    ) -> int:
        """Bulk update model instances while maintaining updated_at/version semantics."""
        objs = list(objs)
        now = timezone.now()
        fields = list(fields)

        supports_updated_at = self._has_model_field("updated_at")
        supports_updated_by = self._has_model_field("updated_by")
        supports_version = self._has_model_field("version")

        if supports_updated_at and "updated_at" not in fields:
            fields.append("updated_at")
        if supports_updated_by and "updated_by" not in fields:
            fields.append("updated_by")
        if supports_version and "version" not in fields:
            fields.append("version")

        for obj in objs:
            if supports_updated_at:
                obj.updated_at = now
            if supports_updated_by:
                obj.updated_by = get_current_actor()
            if supports_version:
                current = getattr(obj, "version", 1) or 1
                obj.version = current + 1

        return super().bulk_update(objs, fields, batch_size=batch_size)

    def update_without_version(self, **kwargs: Any) -> int:
        """Update rows without bumping `version` (still sets `updated_at` unless provided)."""
        now = timezone.now()
        if self._has_model_field("updated_at") and "updated_at" not in kwargs:
            kwargs["updated_at"] = now
        return super().update(**kwargs)

    def _has_model_field(self, name: str) -> bool:
        """Check if `name` is a Django-managed field/relation on this model."""
        if hasattr(self.model, "_field_cache"):
            if name in self.model._field_cache:
                return self.model._field_cache[name]
            self.model._field_cache = {}

        val = model_has_field(self.model, name)
        self.model._field_cache[name] = val
        return val


class BaseQuerySet(BulkConsistencyQuerySetMixin, QuerySet):
    """Canonical QuerySet for this repo.

    Composition
    -----------
    - BulkConsistencyQuerySetMixin: `update()`, `bulk_update()`, `update_without_version()`
    """


class SoftDeleteQuerySet(SoftDeleteQuerySetMixin, BulkConsistencyQuerySetMixin, QuerySet):
    """QuerySet with soft delete semantics.

    Composition
    -----------
    - SoftDeleteQuerySetMixin: `active()`, `deleted()`, `soft_delete()`, `restore()`, `hard_delete()`
    - BulkConsistencyQuerySetMixin: `update()`, `bulk_update()`, `update_without_version()`
    """
