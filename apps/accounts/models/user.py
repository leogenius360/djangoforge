"""
User account model.

Goals
-----
- Keep identity + profile concerns in accounts.
- Keep authentication credentials in authn.
- Keep session management in sessions.
- Link the user to a canonical Principal row (AUTH_USER_MODEL) for
  session ownership, lifecycle, and Django auth.

Architecture
------------
``UserAccount`` is NOT ``AbstractBaseUser``.  The project's AUTH_USER_MODEL
is ``Principal``.  UserAccount stores user-specific profile data and
delegates all authentication and lifecycle concerns to its linked Principal.

``username`` lives on Principal (``Principal.username``), not on UserAccount.
``email`` lives on Principal (``Principal.email``), not on UserAccount.
"""

from __future__ import annotations

from typing import Any

from django.db import models, transaction

from apps.core.models import SoftDeleteModel


class UserAccount(SoftDeleteModel):
    """
    User account profile storing user-specific data.

    Links to ``Principal`` for session ownership and lifecycle management.
    All lifecycle state (locked, suspended, disabled, expired) is managed
    by Principal.  Username, email, phone, display_name are stored on
    Principal, not here.

    Fields
    ------
    principal:
        OneToOne link to the AUTH_USER_MODEL (Principal).
    given_name / family_name / middle_name / nickname:
        Personal name fields.
    picture_url:
        URL to user's profile picture.
    gender / birth_date:
        Demographics (optional).
    website_url / bio:
        User profile links and bio.
    metadata:
        User-specific JSON metadata (separate from Principal metadata).
    """

    principal = models.OneToOneField(
        "accounts.Principal",
        on_delete=models.PROTECT,
        related_name="user_account",
        help_text="Canonical principal row for sessions, authentication, and lifecycle.",
    )

    given_name = models.CharField(max_length=64, blank=True, default="")
    family_name = models.CharField(max_length=64, blank=True, default="")
    middle_name = models.CharField(max_length=64, blank=True, default="")
    nickname = models.CharField(max_length=64, blank=True, default="")

    picture_url = models.URLField(blank=True, default="")
    gender = models.CharField(max_length=50, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)

    website_url = models.URLField(blank=True, default="")
    bio = models.TextField(max_length=1000, blank=True, default="")

    metadata = models.JSONField(default=dict, blank=True)

    class Meta(SoftDeleteModel.Meta):
        db_table = "user_accounts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:
        return self.display_name or self.username or f"UserAccount<{self.pk}>"

    def __repr__(self) -> str:
        return f"<UserAccount(id={self.pk}, principal_id={self.principal_id})>"

    # ------------------------------------------------------------------
    # Delegating properties (identity lives on Principal)
    # ------------------------------------------------------------------

    @property
    def username(self) -> str:
        """Delegate username to Principal. Username is stored on the AUTH_USER_MODEL."""
        return self.principal.username

    @property
    def email(self) -> str | None:
        """Delegate email to Principal. Email is stored on the AUTH_USER_MODEL."""
        return self.principal.email

    @property
    def phone_number(self) -> str | None:
        """Delegate phone number to Principal. Phone number is stored on the AUTH_USER_MODEL."""
        return self.principal.phone_number

    @property
    def display_name(self) -> str:
        """Delegate display name to Principal. Display name is stored on the AUTH_USER_MODEL."""
        return self.principal.display_name

    # ------------------------------------------------------------------
    # Delegating properties (lifecycle lives on Principal)
    # ------------------------------------------------------------------

    @property
    def is_locked(self) -> bool:
        """Delegate lock check to Principal."""
        return self.principal.is_locked

    @property
    def is_suspended(self) -> bool:
        """Delegate suspension check to Principal."""
        return self.principal.is_suspended

    @property
    def is_disabled(self) -> bool:
        """Delegate disabled check to Principal."""
        return self.principal.is_disabled

    @property
    def can_authenticate(self) -> bool:
        """
        Canonical authentication gate for user lifecycle.

        Checks user-specific concerns (soft-delete), then delegates
        to Principal for all lifecycle checks.
        """
        if self.is_deleted:
            return False
        return self.principal.can_authenticate

    # ------------------------------------------------------------------
    # Verification properties
    # ------------------------------------------------------------------

    @property
    def is_email_verified(self) -> bool:
        """Return True if email_verified_at is set."""
        return self.principal.is_email_verified

    @property
    def is_phone_verified(self) -> bool:
        """Return True if phone_verified_at is set."""
        return self.principal.is_phone_verified

    # ------------------------------------------------------------------
    # Display name sync (explicit, replaces signal-based sync)
    # ------------------------------------------------------------------

    def sync_display_name(self) -> None:
        """
        Explicitly sync display_name to the linked Principal.

        Replaces the old signal-based pattern.  Call this after
        updating ``display_name`` on the UserAccount.
        """
        name = self.display_name or self.username or ""
        self.principal.set_display_name(name)

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------

    def soft_delete(
        self,
        *,
        actor: Any | None = None,
        using: str | None = None,
        update_fields: set[str] | None = None,
    ) -> tuple[int, dict[str, int]]:
        """
        Soft delete the user account (GDPR-style erasure semantics).

        Delegates to Principal for session invalidation and lifecycle state.
        """
        if self.deleted_at is not None:
            return 0, {self._meta.label: 0}

        with transaction.atomic(using=using, savepoint=False):
            result = super().soft_delete(
                actor=actor,
                using=using,
                update_fields=update_fields,
            )
            self.principal.soft_delete(actor=actor, using=using)

        return result

    def record_successful_login(self, *, ip_address: str | None = None, user_agent: str | None = None) -> None:
        """
        Record a successful login (updates last_seen_at and last_login on Principal).

        Note: IP and user_agent tracking should be handled by the sessions layer.
        Both ``last_login`` and ``last_seen_at`` are stored on Principal.
        """
        self.principal.record_successful_login(ip_address=ip_address, user_agent=user_agent)

    # ------------------------------------------------------------------
    # Save override
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs) -> None:
        """Save UserAccount profile."""
        super().save(*args, **kwargs)
