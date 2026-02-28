"""
APIClient principal subtype for OAuth/OIDC client applications.

This model stores:
- OAuth client properties (client_id, secret hash, redirect URIs, scopes, grant types)
- Ownership metadata
- Links to a canonical Principal row for session ownership

Architecture
------------
APIClient is a **profile** for API client principals.  All identity,
lifecycle, and expiry fields live on Principal.  APIClient stores only
OAuth/OIDC-specific configuration.

Security notes
--------------
- ``client_secret`` must be produced by a strong password hash (argon2/bcrypt).
- Never store plaintext secrets.

Principal creation is NOT automatic on save.  The API / service layer is
responsible for creating the Principal first and passing it to APIClient.
Owner FK references Principal (kind=user), not UserAccount.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import SoftDeleteModel


class APIClient(SoftDeleteModel):
    """
    OAuth / OIDC client identity profile.

    Links to ``Principal`` for session ownership and lifecycle management.
    All lifecycle state, expiry, and common identity fields are delegated
    to the linked Principal.

    Fields
    ------
    principal:
        OneToOne link to the AUTH_USER_MODEL (Principal).
    client_id:
        Unique public client identifier.
    client_secret:
        Hashed client secret (never store plaintext).
    client_type:
        OAuth client type (confidential or public).
    redirect_uris:
        JSON list of allowed redirect URIs.
    allowed_scopes:
        JSON list of allowed OAuth scopes.
    grant_types:
        JSON list of allowed OAuth grant types.
    owner:
        FK to user Principal who created/manages this client.
    website_url / terms_url / privacy_url:
        Client application metadata URLs.
    metadata:
        Client-specific JSON metadata (separate from Principal metadata).
    """

    class ClientType(models.TextChoices):
        CONFIDENTIAL = "confidential", "Confidential"
        PUBLIC = "public", "Public"

    principal = models.OneToOneField(
        "accounts.Principal",
        on_delete=models.PROTECT,
        related_name="api_client",
        help_text="Canonical principal for session ownership and stamp invalidation.",
    )

    client_id = models.CharField(max_length=255, unique=True, db_index=True)
    client_secret = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Hashed client secret.  Never store plaintext.",
    )

    client_type = models.CharField(max_length=20, choices=ClientType.choices, default=ClientType.CONFIDENTIAL)

    redirect_uris = models.JSONField(default=list, blank=True)
    allowed_scopes = models.JSONField(default=list, blank=True)
    grant_types = models.JSONField(default=list, blank=True)

    owner = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_api_clients",
        limit_choices_to={"kind": "user"},
        help_text="User principal who owns/manages this API client.",
    )

    website_url = models.URLField(blank=True, default="")
    terms_url = models.URLField(blank=True, default="")
    privacy_url = models.URLField(blank=True, default="")

    metadata = models.JSONField(default=dict, blank=True)

    class Meta(SoftDeleteModel.Meta):
        db_table = "api_clients"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client_id"]),
            models.Index(fields=["owner"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:
        return self.display_name or self.client_id or f"APIClient<{self.pk}>"

    def __repr__(self) -> str:
        return f"<APIClient(id={self.pk}, client_id={self.client_id!r})>"

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
        API client can authenticate if principal allows it and
        the client is not soft-deleted.
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

        Uses ``client_id`` as the display name.
        """
        self.principal.set_display_name(self.client_id)
