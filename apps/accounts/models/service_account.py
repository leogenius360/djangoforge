"""
Service account (machine/service) principal subtype.

A ServiceAccount row links to a canonical Principal row:
- Principal.kind = SERVICE
- Sessions reference Principal (not the service model directly).

Architecture
------------
ServiceAccount is a **profile** for machine/service principals.  All identity,
lifecycle, and expiry fields live on Principal.  ServiceAccount stores only
service-specific configuration (scopes, owner, service_name, description).

Principal creation is NOT automatic on save.  The API / service layer is
responsible for creating the Principal first and passing it to ServiceAccount.
This keeps the model layer free of implicit side effects and makes transactional
boundaries explicit.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import SoftDeleteModel


class ServiceAccount(SoftDeleteModel):
    """
    Machine / service identity profile for M2M authentication.

    Links to ``Principal`` for session ownership and lifecycle management.
    All lifecycle state, expiry, and common identity fields are delegated
    to the linked Principal.

    Fields
    ------
    principal:
        OneToOne link to the AUTH_USER_MODEL (Principal).
    name:
        Unique human-readable identifier.
    service_name:
        Logical service name (e.g., "payment-gateway").
    description:
        Free-text description of the service account's purpose.
    owner:
        FK to the user Principal who owns/manages this service account.
    allowed_scopes:
        JSON list of OAuth/authorization scopes this service is allowed.
    metadata:
        Service-specific JSON metadata (separate from Principal metadata).
    """

    principal = models.OneToOneField(
        "accounts.Principal",
        on_delete=models.PROTECT,
        related_name="service_account",
        help_text="Canonical principal for session ownership.",
    )

    name = models.CharField(max_length=150, unique=True)
    service_name = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, default="")

    owner = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_service_accounts",
        limit_choices_to={"kind": "user"},
        help_text="User principal who owns/manages this service account.",
    )

    allowed_scopes = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(SoftDeleteModel.Meta):
        db_table = "service_accounts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["service_name"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:
        return self.display_name or self.service_name or f"ServiceAccount<{self.pk}>"

    def __repr__(self) -> str:
        return f"<ServiceAccount(id={self.pk}, service_name={self.service_name!r})>"

    # ------------------------------------------------------------------
    # Delegating properties (identity lives on Principal)
    # ------------------------------------------------------------------

    @property
    def username(self) -> str:
        """Delegate username to Principal."""
        return self.principal.username

    @property
    def display_name(self) -> str:
        """Delegate display name to Principal."""
        return self.principal.display_name

    # ------------------------------------------------------------------
    # Delegating properties (lifecycle lives on Principal)
    # ------------------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """Delegate expiry check to Principal."""
        return self.principal.is_expired

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
        Service account can authenticate if principal allows it and
        the account is not soft-deleted.
        """
        if self.is_deleted:
            return False
        return self.principal.can_authenticate

    # ------------------------------------------------------------------
    # Display name sync (explicit, replaces signal-based sync)
    # ------------------------------------------------------------------

    def sync_display_name(self) -> None:
        """
        Explicitly sync display_name to the linked Principal.

        Uses ``service_name`` falling back to ``name``.
        """
        name = self.service_name or self.name
        self.principal.set_display_name(name)
