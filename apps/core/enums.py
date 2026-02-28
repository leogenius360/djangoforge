from django.db.models import TextChoices


class CoreStatus(TextChoices):
    """
    Base lifecycle status for models with state management.

    Used as a foundation for lifecycle state machines across the application.
    Can be extended by domain-specific apps for additional states.

    States
    ------
    ACTIVE
        Default operational state. Entity is fully functional.

    DISABLED
        Administratively disabled. Entity exists but is non-operational.
        Requires `disabled_at` to be set.

    LOCKED
        Temporarily restricted due to security concerns (e.g., failed auth attempts).
        Requires `locked_at` and `locked_until` to be set.
        Auto-unlocks when `locked_until` is in the past.

    SUSPENDED
        Policy-based suspension (e.g., terms violation, fraud).
        Requires `suspended_at` to be set.

    DELETED
        Soft-deleted state. Entity is logically deleted but data is retained.
        Used with `deleted_at` field.

    Default Transitions
    -------------------
    - ACTIVE → DISABLED, LOCKED, SUSPENDED, DELETED
    - LOCKED → ACTIVE, DISABLED, SUSPENDED, DELETED
    - SUSPENDED → ACTIVE, DISABLED, DELETED
    - DISABLED → ACTIVE, DELETED
    - DELETED → ACTIVE (restoration)

    Notes
    -----
    LOCKED, SUSPENDED, and DELETED states prevent certain actions including
    modifications and unauthorized access. Enforcement varies by domain.

    Models using LifecycleMixin can customize allowed transitions by overriding
    the ALLOWED_TRANSITIONS class attribute.
    """

    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"
    LOCKED = "locked", "Locked"
    SUSPENDED = "suspended", "Suspended"
    DELETED = "deleted", "Deleted"
