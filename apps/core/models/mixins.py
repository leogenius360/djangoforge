"""
Core Django model mixins for lifecycle + soft-delete + actor attribution + optimistic locking.

Design goals
------------
1) Composable field mixins:
   Most mixins only declare fields + helper methods.

2) No MRO surprises:
   Exactly one mixin (ModelOperationsMixin) overrides save()/delete().

3) Deterministic invariants:
   - update_fields safety: updated_at cannot be skipped when present
   - optional optimistic locking: version conflict raises OptimisticLockError
   - soft delete: if deleted_at exists, delete() is a soft delete
   - lifecycle coherence: validated before writes (friendlier than DB constraint errors)
   - actor attribution: async-safe contextvars, strict enforcement optional

Recommended composition order
-----------------------------
class MyModel(
    ModelOperationsMixin,      # must be first: orchestrates save/delete
    BaseActorMixin,            # stamps created_by/updated_by
    LifecycleMixin,            # lifecycle state machine + helpers + hooks
    SoftDeleteMixin,           # deleted_at + deleted_by (optional)
    TimestampMixin,            # created_at/updated_at
    models.Model,
):
    ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import models, transaction
from django.utils import timezone

from apps.core.config import get_default_lock_duration, get_enforce_actor
from apps.core.context import get_current_actor, require_actor, set_current_actor
from apps.core.exceptions import LifecycleStateError, OptimisticLockError
from apps.core.utils.models import get_has_field_callable, model_has_field
from apps.core.validators.lifecycle import LifecycleValidator

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import timedelta

    from apps.core.models import SoftDeleteManager

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Enforcement warnings
# -----------------------------------------------------------------------------


def _warn_enforce_actor_without_actor_fields(model_cls: type[models.Model]) -> None:
    """
    Warn (once per model class, per enforce-value) if actor enforcement is enabled
    but the model has no actor fields to store attribution.

    This remains a warning (not an error) to avoid breaking runtime behavior.
    """
    enforce = bool(get_enforce_actor())
    if not enforce:
        return

    has_field = get_has_field_callable(model_cls)

    actor_field_names = {
        "created_by",
        "updated_by",
        "deleted_by",
        "disabled_by",
        "locked_by",
        "suspended_by",
    }

    if any(has_field(name) for name in actor_field_names):
        return

    warned_attr = "__core_enforce_actor_warned_no_fields_for_value__"
    if getattr(model_cls, warned_attr, None) == enforce:
        return

    setattr(model_cls, warned_attr, enforce)
    label = getattr(getattr(model_cls, "_meta", None), "label", None) or model_cls.__name__
    logger.warning(
        "CORE_ENFORCE_ACTOR is enabled, but %s defines no actor fields; actor attribution cannot be stored.",
        label,
        extra={"model": label},
    )


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


def _save_with_actor(instance: models.Model, *, actor, using, update_fields):
    """Save the instance, wrapping in actor context if actor is available."""
    if actor is not None:
        with set_current_actor(actor):
            instance.save(using=using, update_fields=update_fields)
    else:
        instance.save(using=using, update_fields=update_fields)


# -----------------------------------------------------------------------------
# Timestamp mixin
# -----------------------------------------------------------------------------


class TimestampMixin(models.Model):
    """
    Adds created_at/updated_at timestamps.

    Instance-level update_fields safety is enforced by ModelOperationsMixin which ensures
    updated_at is included whenever present.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


# -----------------------------------------------------------------------------
# Soft delete mixins
# -----------------------------------------------------------------------------


class SoftDeleteMixin(models.Model):
    """
    Adds deleted_at + helpers.

    This mixin does NOT override delete(). ModelOperationsMixin.delete() provides
    the canonical soft delete behavior when present.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        """Return True if deleted_at is set."""
        return self.deleted_at is not None

    def soft_delete(
        self,
        *,
        actor=None,
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> tuple[int, dict[str, int]]:
        """
        Soft delete this instance by setting deleted_at.

        Args:
            actor: Principal responsible for the deletion (optional).
            using: Optional DB alias.
            update_fields: Additional caller-provided fields to include in the save.
                Merged with the fields this method manages internally.

        Returns:
            (count, details): Django-like delete tuple.
        """
        if self.is_deleted:
            return 0, {self._meta.label: 0}

        has_field = get_has_field_callable(self.__class__)

        managed_fields: set[str] = set(update_fields or [])
        self.deleted_at = timezone.now()
        managed_fields.add("deleted_at")

        resolved_actor = actor or get_current_actor()
        if resolved_actor is not None and has_field("deleted_by"):
            self.deleted_by = resolved_actor
            managed_fields.add("deleted_by")

        _save_with_actor(
            self,
            actor=resolved_actor,
            using=using,
            update_fields=managed_fields if update_fields is not None else None,
        )
        return 1, {self._meta.label: 1}

    def restore(self, *, actor=None, using: str | None = None) -> None:
        """
        Restore a soft-deleted instance by clearing deleted_at.

        If lifecycle exists, status is recomputed deterministically from fields when possible.
        """
        if self.deleted_at is None:
            return

        has_field = get_has_field_callable(self.__class__)

        update_fields: set[str] = {"deleted_at"}
        self.deleted_at = None

        resolved_actor = actor or get_current_actor()
        if resolved_actor is not None and has_field("deleted_by"):
            self.deleted_by = None
            update_fields.add("deleted_by")

        _save_with_actor(self, actor=resolved_actor, using=using, update_fields=update_fields)


# -----------------------------------------------------------------------------
# Actor stamping mixin
# -----------------------------------------------------------------------------


class BaseActorMixin(models.Model):
    """
    Tracks who created/updated a row.

    Does not override save(); provides an orchestration hook `_track_actor()`.
    """

    created_by = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
    )
    updated_by = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_%(class)ss",
    )

    ACTOR_REQUIRED: bool | None = None  # Tri-state: True=always enforce, False=never, None=defer to global setting.

    class Meta:
        abstract = True

    @property
    def actor_required(self) -> bool:
        """
        Return True if this instance requires an actor for creates/updates/deletes.

        Tri-state resolution:
          - ACTOR_REQUIRED is True  → enforce if model has actor fields
          - ACTOR_REQUIRED is False → never enforce (explicit opt-out)
          - ACTOR_REQUIRED is None  → defer to global CORE_ENFORCE_ACTOR setting
        """
        has_field = get_has_field_callable(self.__class__)
        has_actor_field = any(has_field(name) for name in ("created_by", "updated_by", "deleted_by"))
        if not has_actor_field:
            return False
        if self.ACTOR_REQUIRED is not None:
            return self.ACTOR_REQUIRED
        # None → defer to global setting
        return get_enforce_actor()

    def _set_actor(
        self, actor, *, is_insert: bool = False, is_delete: bool = False, update_fields: set[str] | None = None
    ) -> set[str] | None:
        """
        Stamp actor fields deterministically when actor is present.

        Behavior:
          - created_by: set on insert if not already set
          - updated_by: set on any save when actor present
          - deleted_by: set on delete when actor present (if field exists)

        Returns:
            Updated update_fields set (or None).
        """
        if actor is None:
            if self.actor_required:
                raise ValueError(
                    "An actor (Principal) is required for this operation. "
                    "Provide `actor=...` or set one via set_current_actor(). "
                    "For automated flows, use require_system_actor()."
                )
            return update_fields

        has_field = get_has_field_callable(self.__class__)

        if is_insert and has_field("created_by") and getattr(self, "created_by", None) is None:
            self.created_by = actor
            if update_fields is not None:
                update_fields.add("created_by")

        if has_field("updated_by"):
            self.updated_by = actor
            if update_fields is not None:
                update_fields.add("updated_by")

        if is_delete and has_field("deleted_by"):
            self.deleted_by = actor
            if update_fields is not None:
                update_fields.add("deleted_by")

        return update_fields


# -----------------------------------------------------------------------------
# Lifecycle fields + transitions + hooks (Improvement #3)
# -----------------------------------------------------------------------------


class LifecycleMixin(models.Model):
    """
    Adds lifecycle/status fields + audit metadata + deterministic transition helpers.
    """

    # Public api status (visibility and availability).
    is_active = models.BooleanField(default=True, db_index=True)
    disabled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    disabled_by = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disabled_%(class)ss",
    )
    disabled_reason = models.CharField(max_length=255, blank=True, default="")

    # System-enforced locks (security enforcement).
    locked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    locked_until = models.DateTimeField(null=True, blank=True, db_index=True)
    locked_by = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_%(class)ss",
    )
    locked_reason = models.CharField(max_length=255, blank=True, default="")

    # Administrative suspensions (policy enforcement).
    suspended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    suspended_by = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suspended_%(class)ss",
    )
    suspended_reason = models.CharField(max_length=255, blank=True, default="")

    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    LIFECYCLE_ACTOR_REQUIRED: bool | None = None  # Tri-state: True=always enforce, False=never, None=defer to global.

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_lock_fields_consistent",
                condition=(
                    models.Q(locked_at__isnull=True, locked_until__isnull=True)
                    | models.Q(locked_at__isnull=False, locked_until__isnull=False)
                ),
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_locked_until_gte_locked_at",
                condition=(
                    models.Q(locked_until__isnull=True)
                    | models.Q(locked_at__isnull=True)
                    | models.Q(locked_until__gte=models.F("locked_at"))
                ),
            ),
        ]

    @property
    def lifecycle_actor_required(self) -> bool:
        """
        Return True if this instance requires an actor for lifecycle transitions.

        Tri-state resolution:
          - LIFECYCLE_ACTOR_REQUIRED is True  → enforce if model has lifecycle actor fields
          - LIFECYCLE_ACTOR_REQUIRED is False → never enforce (explicit opt-out)
          - LIFECYCLE_ACTOR_REQUIRED is None  → defer to global CORE_ENFORCE_ACTOR setting
        """
        has_field = get_has_field_callable(self.__class__)
        has_actor_field = any(has_field(name) for name in ("disabled_by", "locked_by", "suspended_by"))
        if not has_actor_field:
            return False
        if self.LIFECYCLE_ACTOR_REQUIRED is not None:
            return self.LIFECYCLE_ACTOR_REQUIRED
        # None → defer to global setting
        return get_enforce_actor()

    @property
    def is_disabled(self) -> bool:
        """Return True if disabled_at is set."""
        return self.disabled_at is not None

    @property
    def is_locked(self) -> bool:
        """Return True if locked_until is set and in the future."""
        return self.locked_until is not None and timezone.now() < self.locked_until

    @property
    def is_suspended(self) -> bool:
        """Return True if suspended_at is set."""
        return self.suspended_at is not None

    @property
    def is_expired(self) -> bool:
        """Return True if expires_at is set and in the past."""
        if self.expires_at is None:
            return False

        now = timezone.now()
        return now >= self.expires_at

    def enable(
        self, *, actor=None, reason: str = "", using: str | None = None, update_fields: set[str] | None = None
    ) -> None:
        """
        Lift the disabled restriction (Visibility enforcement). Idempotent.

        Clears disabled_at/by/reason. Sets is_active=True when no other
        restriction (locked, suspended) remains.

        Args:
            actor: Principal responsible for the change (optional).
            reason: Human-readable reason (optional).
            using: Optional DB alias.
            update_fields: Partial fields to update (optional).
        """
        if not self.is_disabled:
            return
        managed_fields = set(update_fields or [])
        managed_fields.update(self._clear_disabled_fields())
        # is_active is the combined availability flag: set True only when all restrictions are gone.
        if not self.is_locked and not self.is_suspended:
            self.is_active = True
            managed_fields.add("is_active")
        _save_with_actor(
            self, actor=actor, using=using, update_fields=managed_fields if update_fields is not None else None
        )

    def disable(
        self,
        *,
        actor=None,
        reason: str = "",
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Disable the current instance.

        Args:
            actor: Principal responsible for the change (optional).
            reason: Human-readable reason.
            using: Optional DB alias.
            update_fields: Partial fields to update (optional).
        """
        resolved_actor = self._resolve_actor_for("disabled_by", actor=actor)
        managed_fields = set(update_fields or [])
        managed_fields.update(self._set_disabled_fields(actor=resolved_actor, reason=reason or "Disabled"))
        self.is_active = False
        managed_fields.add("is_active")
        _save_with_actor(
            self, actor=resolved_actor, using=using, update_fields=managed_fields if update_fields is not None else None
        )

    def lock(
        self,
        *,
        actor=None,
        reason: str = "",
        duration: timedelta | None = None,
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Lock this instance (Security enforcement).

        Disable, lock, and suspend are independent and can co-exist.

        Args:
            actor: Principal responsible for the lock.
            reason: Human-readable reason.
            duration: Lock duration; defaults to get_default_lock_duration().
            using: Optional DB alias.
            update_fields: Partial fields to update (optional).
        """
        resolved_actor = self._resolve_actor_for("locked_by", actor=actor)
        managed_fields = set(update_fields or [])
        managed_fields.update(
            self._set_locked_fields(actor=resolved_actor, reason=reason or "Locked", duration=duration)
        )
        self.is_active = False
        managed_fields.add("is_active")
        _save_with_actor(
            self, actor=resolved_actor, using=using, update_fields=managed_fields if update_fields is not None else None
        )

    def unlock(
        self,
        *,
        actor=None,
        reason: str = "",
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Lift the lock restriction (Security enforcement). Idempotent.

        Clears locked_at/until/by/reason. Sets is_active=True when no other
        restriction (disabled, suspended) remains.

        Args:
            actor: Principal responsible for the change (optional).
            reason: Human-readable reason (optional).
            using: Optional DB alias.
            update_fields: Partial fields to update (optional).
        """
        if not self.is_locked:
            return
        managed_fields = set(update_fields or [])
        managed_fields.update(self._clear_locked_fields())
        # is_active is the combined availability flag: set True only when all restrictions are gone.
        if not self.is_disabled and not self.is_suspended:
            self.is_active = True
            managed_fields.add("is_active")
        _save_with_actor(
            self, actor=actor, using=using, update_fields=managed_fields if update_fields is not None else None
        )

    def suspend(
        self,
        *,
        actor=None,
        reason: str = "",
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Suspend this instance (Policy enforcement).

        Disable, lock, and suspend are independent and can co-exist.

        Args:
            actor: Principal responsible for the change.
            reason: Human-readable reason.
            using: Optional DB alias.
            update_fields: Partial fields to update (optional).
        """
        resolved_actor = self._resolve_actor_for("suspended_by", actor=actor)
        managed_fields = set(update_fields or [])
        managed_fields.update(self._set_suspended_fields(actor=resolved_actor, reason=reason or "Suspended"))
        self.is_active = False
        managed_fields.add("is_active")
        _save_with_actor(
            self,
            actor=resolved_actor,
            using=using,
            update_fields=managed_fields if update_fields is not None else None,
        )

    def unsuspend(
        self,
        *,
        actor=None,
        reason: str = "",
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Lift the suspension restriction (Policy enforcement). Idempotent.

        Clears suspended_at/by/reason. Sets is_active=True when no other
        restriction (disabled, locked) remains.

        Args:
            actor: Principal responsible for the change (optional).
            reason: Human-readable reason (optional).
            using: Optional DB alias.
            update_fields: Partial fields to update (optional).
        """
        if not self.is_suspended:
            return
        managed_fields = set(update_fields or [])
        managed_fields.update(self._clear_suspended_fields())
        # is_active is the combined availability flag: set True only when all restrictions are gone.
        if not self.is_disabled and not self.is_locked:
            self.is_active = True
            managed_fields.add("is_active")
        _save_with_actor(
            self, actor=actor, using=using, update_fields=managed_fields if update_fields is not None else None
        )

    # ------------------------------------------------------------------
    # Internal helper methods
    # ------------------------------------------------------------------

    def _resolve_actor_for(self, field_name: str, *, actor=None, message: str = None) -> Any:
        """
        Require a non-null actor if enforcement is enabled and field exists.

        Args:
            actor: Candidate actor.
            field_name: Actor field to check (e.g., 'disabled_by').
            message: Error message to raise if required.

        Raises:
            LifecycleStateError: if actor is required but missing.
        """
        _message = message or (
            f"An actor ({field_name}: Principal) is required for state transitions. "
            "Provide `actor=...` or set one via set_current_actor(). "
            "For automated flows, use require_system_actor()."
        )
        has_field = get_has_field_callable(self.__class__)
        resolved_actor = actor or get_current_actor()
        if self.lifecycle_actor_required and has_field(field_name) and resolved_actor is None:
            raise LifecycleStateError(_message)
        return resolved_actor

    def _set_disabled_fields(self, *, actor=None, reason: str) -> set[str]:
        """
        Mutate fields for DISABLED state.

        Args:
            actor: Principal responsible for the transition.
            reason: Human-readable reason (clamped to 255 chars).

        Returns:
            Mutated field names.
        """
        resolved_actor = self._resolve_actor_for("disabled_by", actor=actor)
        self.disabled_at = timezone.now()
        self.disabled_by = resolved_actor
        self.disabled_reason = (reason or "Disabled")[:255]
        return {"disabled_at", "disabled_by", "disabled_reason"}

    def _set_locked_fields(self, *, actor=None, duration: timedelta | None, reason: str) -> set[str]:
        """
        Mutate fields for LOCKED state.

        Args:
            actor: Principal responsible for the lock.
            duration: Lock duration; defaults to get_default_lock_duration().
            reason: Human-readable reason (clamped to 255 chars).

        Returns:
            Mutated field names.
        """
        resolved_actor = self._resolve_actor_for("locked_by", actor=actor)

        if duration is None:
            duration = get_default_lock_duration()

        now = timezone.now()
        self.locked_at = now
        self.locked_until = now + duration
        self.locked_by = resolved_actor
        self.locked_reason = (reason or "Locked")[:255]
        return {"locked_at", "locked_until", "locked_by", "locked_reason"}

    def _set_suspended_fields(self, *, actor=None, reason: str) -> set[str]:
        """
        Mutate fields for SUSPENDED state.

        Args:
            actor: Principal responsible for the transition.
            reason: Human-readable reason (clamped to 255 chars).

        Returns:
            Mutated field names.
        """
        resolved_actor = self._resolve_actor_for("suspended_by", actor=actor)
        self.suspended_at = timezone.now()
        self.suspended_by = resolved_actor
        self.suspended_reason = (reason or "Suspended")[:255]
        return {"suspended_at", "suspended_by", "suspended_reason"}

    def _clear_disabled_fields(self) -> set[str]:
        """Clear disabled-specific restriction fields. Returns mutated field names."""
        self.disabled_at = None
        self.disabled_by = None
        self.disabled_reason = ""
        return {"disabled_at", "disabled_by", "disabled_reason"}

    def _clear_locked_fields(self) -> set[str]:
        """Clear lock-specific restriction fields. Returns mutated field names."""
        self.locked_at = None
        self.locked_until = None
        self.locked_by = None
        self.locked_reason = ""
        return {"locked_at", "locked_until", "locked_by", "locked_reason"}

    def _clear_suspended_fields(self) -> set[str]:
        """Clear suspended-specific restriction fields. Returns mutated field names."""
        self.suspended_at = None
        self.suspended_by = None
        self.suspended_reason = ""
        return {"suspended_at", "suspended_by", "suspended_reason"}

    def _validate_lifecycle(self) -> None:
        """
        Validate lifecycle coherence using LifecycleValidator.
        """
        has_field = get_has_field_callable(self.__class__)
        LifecycleValidator.validate(self, has_field)


# -----------------------------------------------------------------------------
# Orchestration (single save/delete override point)
# -----------------------------------------------------------------------------


class ModelOperationsMixin(models.Model):
    """
    The ONLY mixin that overrides save() and delete().

    Enforces deterministic invariants at instance level:
      - Centralized validation (LifecycleValidator)
      - update_fields safety: always includes updated_at when present
      - optional optimistic locking: version checked under SELECT FOR UPDATE, then bumped
      - actor enforcement (optional): require actor if model can store attribution
      - canonical soft delete behavior when deleted_at exists
      - deterministic update_fields ordering at DB boundary
    """

    _field_cache: dict[str, bool] = {}

    class Meta:
        abstract = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._field_cache = {}

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """
        Save with deterministic enterprise invariants.

        Applies:
          - lifecycle validation
          - update_fields safety (updated_at)
          - actor stamping (if supported)
          - status-change tracking
          - optimistic lock bump (if version exists)
        """
        actor = get_current_actor()
        managed_fields = None if update_fields is None else set(update_fields)
        self._save_internal(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=managed_fields,
            bump_version=True,
            actor=actor,
        )

    def save_without_version_bump(
        self,
        *,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Save without bumping version.

        Intended for rare internal operations (e.g., backfills).
        Bulk operations should use queryset-level helpers.
        """
        actor = get_current_actor()
        self._save_internal(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
            bump_version=False,
            actor=actor,
        )

    def delete(self, using: str | None = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        """
        Delete the instance.

        If deleted_at exists, performs a soft delete (sets deleted_at and status=DELETED if present).
        Otherwise, performs a physical delete.

        Returns:
            (count, details): Django-like delete tuple.
        """
        if self._has_field("deleted_at"):
            if getattr(self, "deleted_at", None) is not None:
                return 0, {self._meta.label: 0}

            actor = get_current_actor()
            if (
                get_enforce_actor()
                and actor is None
                and (self._has_field("updated_by") or self._has_field("deleted_by"))
            ):
                actor = require_actor(None)

            update_fields: set[str] = {"deleted_at"}
            self.deleted_at = timezone.now()

            self._save_internal(
                force_insert=False,
                force_update=False,
                using=using,
                update_fields=update_fields,
                bump_version=True,
                actor=actor,
                is_delete=True,
            )
            return 1, {self._meta.label: 1}

        return super().delete(using=using, keep_parents=keep_parents)

    def hard_delete(self, using: str | None = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        """
        Physically delete the instance, bypassing soft delete even if deleted_at exists.
        """
        return super().delete(using=using, keep_parents=keep_parents)

    def _is_insert_mode(self, *, force_insert: bool) -> bool:
        """
        Determine whether this save is an INSERT.

        Args:
            force_insert: Django force_insert flag.

        Returns:
            True if insert, otherwise False.
        """
        return (not self.pk) or self._state.adding or force_insert

    def _normalize_update_fields(self, update_fields: set[str] | None) -> set[str] | None:
        """
        Normalize update_fields into a set (or None).

        Args:
            update_fields: Candidate update_fields.

        Returns:
            A set or None.
        """
        if update_fields is None:
            return None
        return update_fields if isinstance(update_fields, set) else set(update_fields)

    def _get_manager(self, *, using: str | None):
        """
        Return a base manager suitable for optimistic lock checks.

        Includes with_deleted() if the manager supports it.
        """
        manager: SoftDeleteManager = self.__class__._base_manager
        if using is not None:
            manager = manager.using(using)
        if hasattr(manager, "with_deleted"):
            manager = manager.with_deleted()
        return manager

    def _save_with_optimistic_lock(
        self,
        *,
        force_insert: bool,
        force_update: bool,
        using: str | None,
        update_fields: set[str] | None,
        actor,
    ) -> None:
        """
        Save using optimistic locking semantics when 'version' field exists.

        Locks the row (SELECT FOR UPDATE), compares expected version, then bumps version
        and performs the save within the same transaction.

        Raises:
            OptimisticLockError: on version conflict.
        """
        manager = self._get_manager(using=using)
        expected = int(getattr(self, "version", 1) or 1)

        with transaction.atomic(using=using):
            db_version = manager.select_for_update().filter(pk=self.pk).values_list("version", flat=True).first()
            if db_version is None or int(db_version) != expected:
                actor_for_log = actor or get_current_actor()
                actor_id = getattr(actor_for_log, "pk", None) if actor_for_log is not None else None
                logger.warning(
                    "Optimistic lock conflict for %s(pk=%s): expected version=%s.",
                    self._meta.label,
                    self.pk,
                    expected,
                    extra={
                        "model": self._meta.label,
                        "pk": self.pk,
                        "expected_version": expected,
                        "db_version": db_version,
                        "actor_id": actor_id,
                    },
                )
                raise OptimisticLockError(
                    f"Optimistic lock failed for {self._meta.label}({self.pk}): expected version={expected}"
                )

            self.version = expected + 1
            if update_fields is not None:
                update_fields.add("version")

            super().save(
                force_insert=force_insert,
                force_update=force_update,
                using=using,
                update_fields=update_fields,
            )

    def _save_internal(
        self,
        *,
        force_insert: bool,
        force_update: bool,
        using: str | None,
        update_fields: set[str] | None,
        bump_version: bool,
        actor=None,
        is_delete: bool = False,
    ) -> None:
        """
        Internal save orchestration used by save(), delete(), and helpers.

        Applies:
          - centralized validation
          - update_fields safety (updated_at)
          - actor enforcement + stamping
          - optional optimistic locking/version bump
        """
        is_insert = self._is_insert_mode(force_insert=force_insert)
        update_fields = self._normalize_update_fields(update_fields)

        set_actor = getattr(self, "_set_actor", None)
        if callable(set_actor):
            update_fields = set_actor(
                actor=actor,
                is_insert=is_insert,
                is_delete=is_delete,
                update_fields=update_fields,
            )

        if get_enforce_actor():
            _warn_enforce_actor_without_actor_fields(self.__class__)

        # update_fields safety: never skip updated_at on partial updates.
        if update_fields is not None and self._has_field("updated_at"):
            update_fields.add("updated_at")

        lifecycle_validator = getattr(self, "_validate_lifecycle", None)
        if callable(lifecycle_validator):
            # Centralized validation.
            lifecycle_validator()
        elif hasattr(self, "locked_at"):
            LifecycleValidator.validate(self, self._has_field)

        # Optimistic locking: UPDATE only.
        if bump_version and self.__class__._has_field("version") and not is_insert:
            self._save_with_optimistic_lock(
                force_insert=force_insert,
                force_update=force_update,
                using=using,
                update_fields=update_fields,
                actor=actor,
            )
        else:
            super().save(
                force_insert=force_insert,
                force_update=force_update,
                using=using,
                update_fields=update_fields,
            )

    def refresh_from_db(self, using=None, fields=None) -> None:
        """Refresh this instance from the database."""
        super().refresh_from_db(using=using, fields=fields)

    @classmethod
    def _has_field(cls, name: str) -> bool:
        """Check if `name` is a Django-managed field/relation on this model."""
        if name in cls._field_cache:
            return cls._field_cache[name]
        val = model_has_field(cls, name)
        cls._field_cache[name] = val
        return val

    @classmethod
    def clear_field_cache(cls) -> None:
        cls._field_cache.clear()


__all__ = [
    "TimestampMixin",
    "SoftDeleteMixin",
    "BaseActorMixin",
    "LifecycleMixin",
    "ModelOperationsMixin",
]
