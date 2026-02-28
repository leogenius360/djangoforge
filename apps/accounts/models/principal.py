"""
Canonical Principal model -- the project's AUTH_USER_MODEL.

Why this exists
---------------
Principal is the single authenticatable identity for every entity in the system:
users, service accounts, API clients, and agents.  It extends Django's
``AbstractBaseUser`` / ``PermissionsMixin`` so the framework's auth machinery
(``authenticate()``, ``login()``, permissions, admin) works natively.

Each concrete account type (UserAccount, ServiceAccount, APIClient, AgentAccount)
links back to its Principal via a OneToOneField.  Sessions always reference
Principal, never the concrete subtype.

Design notes
------------
- ``username`` is USERNAME_FIELD -- required and unique across all principal kinds.
- ``email`` is optional / nullable -- used for notifications / recovery, not login.
- ``security_stamp`` is a monotonically increasing integer used for
  "logout everywhere" / session-stamp invalidation.
- Lifecycle state (lock, suspend, disable, soft-delete) is managed via
  ``LifecycleMixin`` and associated ``CoreStatus`` transitions.
- No implicit side effects: display_name sync is explicit via ``set_display_name()``.

Compliance alignment
--------------------
- ISO 27001 A.9    -- Access control
- SOC 2 CC6        -- Logical access
- NIST 800-63B     -- Session binding & lifecycle
- OWASP Session Management guidance (invalidation / revocation)
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.enums import PrincipalKind
from apps.accounts.validators import PhoneNumberValidator, UsernameValidator
from apps.core.models import EnterpriseModel

from .managers import PrincipalManager


class Principal(EnterpriseModel, AbstractBaseUser, PermissionsMixin):
    """
    Canonical principal for authentication and session ownership.

    A Principal row exists for every authenticatable entity (user, service
    account, API client, agent).  Sessions always reference this table.

    Fields
    ------
    kind:
        Principal category (user / service / api_client / agent).
    username:
        Unique identifier across all principal kinds.  Used as USERNAME_FIELD.
    email:
        Optional email address (unique if present).  Used for notifications and recovery.
    phone_number:
        Optional phone number (unique if present).  Used for notifications and recovery.
    display_name:
        Optional display name for UI.  Not used for authentication or uniqueness.
    external_id / external_provider:
        Optional fields for linking to external identity providers (e.g., SSO).
    passwordless_enabled:
        Whether passwordless authentication (e.g., magic link) is enabled for this account.
    security_stamp:
        Monotonically increasing integer used to invalidate sessions (bump on lock/suspend/disable/soft-delete).
    is_staff:
        Designates whether the user can log into this admin site.
    last_seen_at:
        Timestamp of last activity (e.g., login).  Updated on successful login.
    tags:
        Optional list of string tags for categorization and filtering.
    metadata:
        Optional JSON blob for arbitrary structured data (e.g., preferences, settings).

    Lifecycle fields (via LifecycleMixin)
    -------------------------------------
    status, expires_at, disabled_at/by/reason, locked_at/until/by/reason,
    suspended_at/by/reason.
    """

    kind = models.CharField(max_length=20, choices=PrincipalKind.choices, db_index=True)

    username_validator = UsernameValidator()
    phone_validator = PhoneNumberValidator()

    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        validators=[username_validator],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )
    email = models.EmailField(
        _("email address"),
        null=True,
        blank=True,
        unique=True,
        help_text=_("Optional. Used for notifications and recovery."),
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)

    phone_number = models.CharField(
        _("phone number"),
        max_length=17,
        blank=True,
        default="",
        validators=[phone_validator],
        db_index=True,
        help_text=_("Optional. Used for notifications and recovery."),
    )
    phone_verified_at = models.DateTimeField(null=True, blank=True)

    display_name = models.CharField(max_length=150, blank=True, default="")

    external_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    external_provider = models.CharField(max_length=50, blank=True, default="")

    passwordless_enabled = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Whether passwordless authentication (e.g., magic link) is enabled for this account."),
    )
    security_stamp = models.BigIntegerField(
        _("security stamp"),
        default=0,
        help_text=_("Bump to invalidate all sessions issued for this principal."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )

    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = ["kind"]
    ACTOR_REQUIRED: bool = True  # For provisioning service to enforce actor presence on create/update/delete operations
    LIFECYCLE_ACTOR_REQUIRED: bool = True  # Require actor for lifecycle transitions (suspend/disable/lock)

    objects = PrincipalManager()

    class Meta:
        db_table = "principals"
        verbose_name = _("principal")
        verbose_name_plural = _("principals")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["kind"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:
        return self.username

    def __repr__(self) -> str:
        return f"<Principal(id={self.pk}, kind={self.kind!r}, username={self.username!r})>"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_email_verified(self) -> bool:
        """Return True if the email address has been verified."""
        return self.email and self.email_verified_at is not None

    @property
    def is_phone_verified(self) -> bool:
        """Return True if the phone number has been verified."""
        return self.phone_number and self.phone_verified_at is not None

    @property
    def can_authenticate(self) -> bool:
        """
        Return True if this principal is allowed to authenticate.

        Intentionally "policy-light" -- a canonical gate that checks:
        - ``is_active`` (Django auth flag)
        - not soft-deleted
        - not disabled
        - not locked
        - not suspended
        - not expired

        Compliance: ISO 27001 A.9.4, NIST 800-63B s7.1.
        """
        if not self.is_active:
            return False
        return not any((self.is_deleted, self.is_disabled, self.is_locked, self.is_suspended, self.is_expired))

    @property
    def is_user(self) -> bool:
        """Return True if this principal represents a user account."""
        return self.kind == PrincipalKind.USER

    @property
    def is_service(self) -> bool:
        """Return True if this principal represents a service account."""
        return self.kind == PrincipalKind.SERVICE

    @property
    def is_api_client(self) -> bool:
        """Return True if this principal represents an API client."""
        return self.kind == PrincipalKind.API_CLIENT

    @property
    def is_agent(self) -> bool:
        """Return True if this principal represents an agent."""
        return self.kind == PrincipalKind.AGENT

    # ------------------------------------------------------------------
    # Display name (explicit, replaces signal-based sync)
    # ------------------------------------------------------------------

    def set_display_name(self, name: str, *, save: bool = True) -> None:
        """
        Explicitly set the display name.

        Replaces the old signal-based sync pattern with an explicit method call.
        Only writes to the database if the value actually changed.

        Parameters
        ----------
        name : str
            New display name.
        save : bool
            If True, persist immediately with ``update_fields``.
        """
        if not name or self.display_name == name:
            return
        self.display_name = name
        if save and self.pk:
            self.save(update_fields=["display_name", "updated_at"])

    # ------------------------------------------------------------------
    # Security stamp
    # ------------------------------------------------------------------

    def bump_security_stamp(self, save: bool = True, update_fields: set[str] | None = None) -> int:
        """
        Bump the security stamp to invalidate all sessions for this principal.

        This is the canonical "logout everywhere" mechanism.

        Parameters
        ----------
        save:
            If True, persist immediately.
        update_fields:
            Additional fields to include in the update when saving (e.g., for lifecycle transitions).

        Returns
        -------
        int
            New stamp value.
        """
        if not save:
            self.security_stamp = int(self.security_stamp or 0) + 1
            return int(self.security_stamp)

        managed_fields = set(update_fields or [])
        managed_fields.update({"security_stamp", "version", "updated_at"})
        if not self.pk:
            self.security_stamp = int(self.security_stamp or 0) + 1
            self.save(update_fields=managed_fields if update_fields is not None else None)
            return int(self.security_stamp)

        # Saved instance: use atomic F() expression to avoid race conditions.
        # The entire block is wrapped in atomic() so that if refresh_from_db or
        # any subsequent step raises, the stamp increment is rolled back and the
        # DB is never left in a bumped-but-unacknowledged state.
        with transaction.atomic(savepoint=False):
            qs = cast("PrincipalManager", type(self).objects).with_deleted().filter(pk=self.pk)
            updated = qs.update(security_stamp=F("security_stamp") + 1)
            if updated != 1:
                raise ValueError(f"Security stamp bump affected {updated} rows (expected 1)")
            self.refresh_from_db(fields=managed_fields if update_fields is not None else None)
        return int(self.security_stamp)

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------
    @transaction.atomic(savepoint=False)
    def lock(
        self,
        *,
        actor: Any | None = None,
        reason: str = "",
        duration: timedelta = timedelta(minutes=30),
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Temporarily lock the account (security control).

        Side effect: bumps ``security_stamp``, invalidating all sessions.

        Compliance: ISO 27001 A.9.4.2 -- automatic lockout on policy violation.
        """
        managed_fields = set(update_fields or set())
        self.bump_security_stamp(save=False, update_fields=managed_fields)
        managed_fields.add("security_stamp")
        return super().lock(
            actor=actor,
            reason=reason or "Account locked",
            duration=duration,
            using=using,
            update_fields=managed_fields if update_fields is not None else None,
        )

    @transaction.atomic(savepoint=False)
    def suspend(
        self,
        *,
        actor: Principal | None = None,
        reason: str = "",
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Suspend account (admin action).

        Side effect: bumps ``security_stamp`` to invalidate sessions.

        Compliance: SOC 2 CC6.1 -- logical access suspension.
        """
        managed_fields = set(update_fields or set())
        self.bump_security_stamp(save=False, update_fields=managed_fields)
        managed_fields.add("security_stamp")
        super().suspend(
            actor=actor,
            reason=reason or "Account suspended",
            using=using,
            update_fields=managed_fields if update_fields is not None else None,
        )

    @transaction.atomic(savepoint=False)
    def disable(
        self,
        *,
        actor: Principal | None = None,
        reason: str = "",
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> None:
        """
        Disable principal and invalidate sessions (stamp bump).

        Compliance: ISO 27001 A.9.2.6 -- removal/adjustment of access rights.
        """
        managed_fields = set(update_fields or set())
        self.bump_security_stamp(save=False, update_fields=managed_fields)
        managed_fields.add("security_stamp")
        super().disable(
            actor=actor,
            reason=reason or "Account disabled",
            using=using,
            update_fields=managed_fields if update_fields is not None else None,
        )

    @transaction.atomic(savepoint=False)
    def soft_delete(
        self,
        *,
        actor: Any | None = None,
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> tuple[int, dict[str, int]]:
        """
        Soft delete principal, align status, and invalidate sessions.

        Compliance: NIST 800-63B s7.1 -- session termination on account deletion.
        """
        if self.deleted_at is not None:
            return 0, {self._meta.label: 0}

        managed_fields = set(update_fields or set())
        self.bump_security_stamp(save=False, update_fields=managed_fields)
        managed_fields.add("security_stamp")
        return super().soft_delete(
            actor=actor, using=using, update_fields=managed_fields if update_fields is not None else None
        )

    # ------------------------------------------------------------------
    # Last-login tracking
    # ------------------------------------------------------------------

    def record_last_login(self) -> None:
        """
        Stamp last_login with the current time and persist without a version bump.

        Wraps the save in ``set_current_actor(self)`` to satisfy
        ``ACTOR_REQUIRED = True`` without requiring an external actor.
        Called by the ``user_logged_in`` signal replacement in
        ``apps.accounts.signals``.
        """
        from django.utils import timezone

        from apps.core.context import set_current_actor

        self.last_login = timezone.now()
        with set_current_actor(self):
            self.save_without_version_bump(update_fields={"last_login"})

    # ------------------------------------------------------------------
    # Save override
    # ------------------------------------------------------------------

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """
        Save Principal.

        - Normalizes username (lowercase if configured).
        - Normalizes empty email to None (avoids unique constraint violations).
        - Clears expired lock fields.
        """
        now = timezone.now()
        managed_fields: set[str] = set()

        # Normalize username
        if self.username:
            normalized = PrincipalManager.normalize_username(self.username)
            if normalized != self.username:
                self.username = normalized
                managed_fields.add("username")

        # Normalize phone number
        if self.phone_number:
            normalized_phone = PrincipalManager.normalize_phone_number(self.phone_number)
            if normalized_phone != self.phone_number:
                self.phone_number = normalized_phone
                managed_fields.add("phone_number")

        # Normalize empty email to None
        if self.email == "":
            self.email = None
            managed_fields.add("email")

        # Clear expired lock
        expired_lock = bool(self.locked_until and now >= self.locked_until)
        if expired_lock:
            managed_fields.update(self._clear_lock_fields())

        if update_fields is not None and managed_fields:
            managed_fields.update(update_fields)
        else:
            managed_fields = None  # Pass None to save() to update all fields

        super().save(force_insert=force_insert, force_update=force_update, using=using, update_fields=managed_fields)
