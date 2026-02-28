"""
Authentication credentials for users.

Credential types:
- Password (hashed via Django hashers)
- WebAuthn / Passkeys (public key storage)
- TOTP (encrypted secret recommended)
- Backup codes (hashed, one-time use)

Security notes:
- Passwords are stored hashed (Django hashers, Argon2 primary).
- WebAuthn uses public keys (non-secret).
- TOTP secrets should be encrypted at rest.
- Backup codes are hashed and one-time use.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteModel

from .enums import CredentialStatus


class BaseCredential(SoftDeleteModel):
    """Abstract credential model.

    Each credential belongs to a user and may be revoked/expired independently.
    Inherits UUID PK, timestamps, version (optimistic locking), and soft-delete
    semantics from ``SoftDeleteModel``.
    """

    principal = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_set",
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=CredentialStatus.choices,
        default=CredentialStatus.ACTIVE,
        db_index=True,
    )
    label = models.CharField(max_length=100, blank=True, default="")
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_expired(self) -> bool:
        """Return True if expires_at is set and in the past."""
        return bool(self.expires_at and timezone.now() > self.expires_at)

    @property
    def is_usable(self) -> bool:
        """Return True if credential is active and not expired."""
        return self.status == CredentialStatus.ACTIVE and not self.is_expired

    def mark_used(self) -> None:
        """Set last_used_at to now."""
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at", "version", "updated_at"])

    def revoke(self) -> None:
        """Mark credential as revoked."""
        self.status = CredentialStatus.REVOKED
        self.save(update_fields=["status", "version", "updated_at"])


class PasswordCredential(BaseCredential):
    """Password credential. Stores hashed password."""

    password_hash = models.CharField(max_length=128)
    strength_score = models.PositiveSmallIntegerField(default=0)
    is_compromised = models.BooleanField(default=False)
    require_change = models.BooleanField(default=False)

    class Meta:
        db_table = "password_credentials"
        indexes = [
            models.Index(fields=["principal"]),
            models.Index(fields=["status"]),
            models.Index(fields=["deleted_at"]),
        ]

    def set_password(self, raw_password: str) -> None:
        """Hash and set the password."""
        self.password_hash = make_password(raw_password)
        self.save(update_fields=["password_hash", "version", "updated_at"])

    def check_password(self, raw_password: str) -> bool:
        """Verify raw password against stored hash."""
        return check_password(raw_password, self.password_hash)


class WebAuthnCredential(BaseCredential):
    """WebAuthn/Passkey credential."""

    credential_id = models.TextField(unique=True, db_index=True)
    public_key = models.TextField()
    sign_count = models.PositiveIntegerField(default=0)
    aaguid = models.CharField(max_length=36, blank=True, default="")
    transports = models.JSONField(default=list, blank=True)

    backup_eligible = models.BooleanField(default=False)
    backup_state = models.BooleanField(default=False)

    class Meta:
        db_table = "webauthn_credentials"
        indexes = [
            models.Index(fields=["principal"]),
            models.Index(fields=["status"]),
            models.Index(fields=["deleted_at"]),
        ]

    def increment_sign_count(self) -> None:
        """Increment signature counter after successful authentication."""
        self.sign_count += 1
        self.mark_used()


class TOTPCredential(BaseCredential):
    """TOTP credential.

    SECURITY: The ``secret`` field should be encrypted at rest using
    field-level encryption.
    """

    secret = models.CharField(max_length=64)
    algorithm = models.CharField(max_length=10, default="SHA1")
    digits = models.PositiveSmallIntegerField(default=6)
    period = models.PositiveSmallIntegerField(default=30)

    class Meta:
        db_table = "totp_credentials"
        indexes = [
            models.Index(fields=["principal"]),
            models.Index(fields=["status"]),
            models.Index(fields=["deleted_at"]),
        ]


class BackupCode(BaseCredential):
    """One-time backup code credential. Code stored hashed."""

    code_hash = models.CharField(max_length=128)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "backup_code_credentials"
        indexes = [
            models.Index(fields=["principal"]),
            models.Index(fields=["status"]),
            models.Index(fields=["deleted_at"]),
        ]

    def verify_and_consume(self, raw_code: str) -> bool:
        """Verify a backup code and consume it.

        Returns True on success, False otherwise.
        """
        if self.is_used:
            return False

        if check_password(raw_code, self.code_hash):
            self.is_used = True
            self.used_at = timezone.now()
            self.status = CredentialStatus.INACTIVE
            self.save(
                update_fields=[
                    "is_used",
                    "used_at",
                    "status",
                    "version",
                    "updated_at",
                ]
            )
            return True

        return False
