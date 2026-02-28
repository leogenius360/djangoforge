"""
Lifecycle validation rules for core models.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.core.config import get_enforce_actor
from apps.core.exceptions import LifecycleStateError

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db import models


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Validation Layer (Improvement #1)
# -----------------------------------------------------------------------------


class LifecycleValidator:
    """
    Centralized, stateless lifecycle validation rules.

    This is intentionally deterministic and does not read from the database.
    """

    @staticmethod
    def validate(instance: models.Model, has_field: Callable[[str], bool]) -> None:
        """
        Validate lifecycle coherence for an instance.

        Args:
            instance: Model instance to validate.
            has_field: Callable for field existence checks (cached if possible).

        Raises:
            LifecycleStateError: if invariants are violated.
        """
        LifecycleValidator.validate_lock_coherence(instance, has_field)
        LifecycleValidator.validate_restriction_fields(instance, has_field)
        LifecycleValidator.validate_is_active_coherence(instance, has_field)

    @staticmethod
    def validate_lock_coherence(instance: models.Model, has_field: Callable[[str], bool]) -> None:
        """
        Validate locked_at/locked_until field-pair coherence.
        """
        if not (has_field("locked_at") and has_field("locked_until")):
            return

        locked_at = getattr(instance, "locked_at", None)
        locked_until = getattr(instance, "locked_until", None)

        if (locked_at is None) ^ (locked_until is None):
            raise LifecycleStateError(
                f"{LifecycleValidator._label_pk(instance)}: locked_at and locked_until must be both null or both set."
            )

        if locked_at is not None and locked_until is not None and locked_until < locked_at:
            raise LifecycleStateError(f"{LifecycleValidator._label_pk(instance)}: locked_until must be >= locked_at.")

        if (
            get_enforce_actor()
            and has_field("locked_by")
            and locked_until is not None
            and not getattr(instance, "locked_by", None)
        ):
            raise LifecycleStateError(f"{LifecycleValidator._label_pk(instance)}: active lock requires locked_by.")

    @staticmethod
    def validate_restriction_fields(instance: models.Model, has_field: Callable[[str], bool]) -> None:
        """
        Validate disabled_by and suspended_by actor requirements when enforcement is enabled.
        """
        if not get_enforce_actor():
            return

        if (
            has_field("disabled_at")
            and has_field("disabled_by")
            and getattr(instance, "disabled_at", None) is not None
            and not getattr(instance, "disabled_by", None)
        ):
            raise LifecycleStateError(f"{LifecycleValidator._label_pk(instance)}: disabled_at requires disabled_by.")

        if (
            has_field("suspended_at")
            and has_field("suspended_by")
            and getattr(instance, "suspended_at", None) is not None
            and not getattr(instance, "suspended_by", None)
        ):
            raise LifecycleStateError(f"{LifecycleValidator._label_pk(instance)}: suspended_at requires suspended_by.")

    @staticmethod
    def validate_is_active_coherence(instance: models.Model, has_field: Callable[[str], bool]) -> None:
        """
        Validate that is_active mirrors the combined restriction state.

        Rules:
        - is_active must be False when any restriction (disabled, locked, suspended) is active.
        - is_active must be True when no restriction is active.
        """
        if not has_field("is_active"):
            return

        is_active = getattr(instance, "is_active", None)
        is_disabled = has_field("disabled_at") and getattr(instance, "disabled_at", None) is not None
        is_locked = has_field("locked_until") and getattr(instance, "locked_until", None) is not None
        is_suspended = has_field("suspended_at") and getattr(instance, "suspended_at", None) is not None
        any_restriction = is_disabled or is_locked or is_suspended

        if any_restriction and is_active:
            active_restrictions = ", ".join(
                r for r, flag in (("disabled", is_disabled), ("locked", is_locked), ("suspended", is_suspended)) if flag
            )
            raise LifecycleStateError(
                f"{LifecycleValidator._label_pk(instance)}: "
                f"is_active must be False when restricted ({active_restrictions})."
            )

        if not any_restriction and is_active is False:
            raise LifecycleStateError(
                f"{LifecycleValidator._label_pk(instance)}: is_active must be True when no restriction is active."
            )

    @staticmethod
    def _label_pk(instance: models.Model) -> str:
        """
        Format a stable, helpful identifier for error messages.
        """
        pk = instance.pk if instance.pk is not None else "unsaved"
        return f"{instance._meta.label}(pk={pk})"
