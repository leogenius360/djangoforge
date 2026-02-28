"""
Project base model classes.

These abstract models compose the mixins from apps.core.models.mixins and attach
your repo's BaseManager.

MRO / side effects
------------------
All base models inherit ModelOperationsMixin first. That mixin is the single override
point for save/delete, keeping behavior consistent regardless of how other mixins are
ordered or combined.

Managers
--------
BaseManager defaults to active() which excludes deleted rows when deleted_at exists.
If deleted_at doesn't exist on a model, BaseQuerySet.active() returns self.
"""

from __future__ import annotations

import uuid

from django.db import models

from .managers import BaseManager, SoftDeleteManager, SoftDeleteManagerMixin
from .mixins import BaseActorMixin, LifecycleMixin, ModelOperationsMixin, SoftDeleteMixin, TimestampMixin
from .querysets import BaseQuerySet, BulkConsistencyQuerySetMixin, SoftDeleteQuerySetMixin


class BaseModel(ModelOperationsMixin, TimestampMixin):
    """
    Minimal project base model.

    Includes
    --------
    - UUID primary key
    - created_at / updated_at timestamps
    - version for optimistic locking
    - BaseManager (safe even if a model doesn't support deleted_at)

    Use this for models that do not need soft delete.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(default=1)

    objects = BaseManager()

    class Meta:
        abstract = True
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        """Return string representation showing model name and ID."""
        return f"{self._meta.verbose_name} ({self.id})"

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return f"<{self.__class__.__name__}(id={self.id})>"


class ActorModel(BaseModel, BaseActorMixin):
    """
    BaseModel + created_by/updated_by fields.

    Note: This does not automatically stamp actors; do that in your service layer
    (or middleware) to keep responsibilities explicit.
    """

    objects = BaseManager()

    class Meta(BaseModel.Meta):
        abstract = True


class SoftDeleteModel(BaseModel, SoftDeleteMixin):
    """
    BaseModel + soft delete.

    Behaviors
    ---------
    - delete() performs soft delete when deleted_at exists (implemented by ModelOperationsMixin)
    - hard_delete() physically deletes
    """

    objects = SoftDeleteManager()

    class Meta(BaseModel.Meta):
        abstract = True


class SoftDeleteActorModel(SoftDeleteModel, BaseActorMixin):
    """
    SoftDeleteModel + created_by/updated_by fields.

    Use this for models that need both soft delete and actor tracking.
    """

    deleted_by = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_%(class)ss",
    )

    objects = SoftDeleteManager()

    class Meta(SoftDeleteModel.Meta):
        abstract = True


class LifecycleModel(SoftDeleteModel, LifecycleMixin):
    """
    SoftDeleteModel + lifecycle fields + status fields and transition helpers.

    Use this for models that store lifecycle metadata and consistent transition methods like lock()/unlock()/disable().
    """

    objects = SoftDeleteManager()

    class Meta(SoftDeleteModel.Meta):
        abstract = True


class EnterpriseModel(SoftDeleteActorModel, LifecycleMixin):
    """
    Full-featured project base model with transition helpers.

    Includes
    --------
    - created_by/updated_by
    - lifecycle fields + inline status audit
    """

    objects = SoftDeleteManager()

    class Meta(SoftDeleteActorModel.Meta):
        abstract = True


__all__ = [
    "BaseModel",
    "SoftDeleteModel",
    "SoftDeleteActorModel",
    "ActorModel",
    "LifecycleModel",
    "EnterpriseModel",
    # Managers
    "BaseManager",
    "SoftDeleteManager",
    "SoftDeleteManagerMixin",
    # Querysets
    "BaseQuerySet",
    "BulkConsistencyQuerySetMixin",
    "SoftDeleteQuerySetMixin",
]
