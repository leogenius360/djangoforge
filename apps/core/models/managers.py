"""
Project-level Manager implementation.

This manager pairs with BaseQuerySet to provide:
- Default behavior: exclude soft-deleted rows
- Opt-in: include deleted rows via `.with_deleted()`
- Convenience filters: `.active()` and `.deleted()`

If you create custom managers using `from_queryset`, ensure the queryset subclasses
BaseQuerySet or you'll lose the bulk update/delete version+updated_at guarantees.
"""

from __future__ import annotations

from typing import cast

from django.db import models

from apps.core.typing import ManagerMixinBase

from .querysets import BaseQuerySet, SoftDeleteQuerySet


class SoftDeleteManagerMixin(ManagerMixinBase):
    """Default to active() and provide with_deleted()/deleted() helpers."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Return the default queryset (non-deleted rows only)."""
        return cast("SoftDeleteQuerySet", super().get_queryset()).active()

    def with_deleted(self) -> SoftDeleteQuerySet:
        """Return a queryset including soft-deleted rows."""
        return super().get_queryset()

    def active(self) -> SoftDeleteQuerySet:
        """Alias for the default active queryset."""
        return self.get_queryset()

    def deleted(self) -> SoftDeleteQuerySet:
        """Return only soft-deleted rows."""
        return self.with_deleted().deleted()


class BaseManager(models.Manager.from_queryset(BaseQuerySet)):
    """Canonical manager for repo models."""


class SoftDeleteManager(SoftDeleteManagerMixin, models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Manager that defaults to active() and provides with_deleted()/deleted()."""
