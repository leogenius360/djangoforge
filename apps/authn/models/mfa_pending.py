"""
MFA pending authentication model.

Replaces cache-based MFA pending state with a persistent, auditable DB record.
The raw MFA token is returned to the client; only its HMAC-SHA256 digest is stored.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteModel


class MFAPendingAuthentication(SoftDeleteModel):
    """Persistent MFA pending state.

    Created when primary authentication succeeds but MFA is required.
    The raw MFA token is sent to the client; only ``token_hash`` (HMAC-SHA256)
    is stored.

    Security properties:
    - Token stored as HMAC hash, never plaintext.
    - ``attempt_count`` / ``max_attempts`` prevents brute-force on MFA codes.
    - ``expires_at`` enforces a strict TTL.
    - ``consumed_at`` prevents replay.
    """

    principal = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mfa_pending_auths",
    )
    token_hash = models.CharField(max_length=64, db_index=True)

    auth_method = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="The primary auth method that was used (password, passwordless, etc.).",
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")

    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)

    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mfa_pending_authentications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token_hash"]),
            models.Index(fields=["principal", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"MFA pending for {self.principal} (expires {self.expires_at})"

    @property
    def is_valid(self) -> bool:
        """Pending record is valid if not consumed, not expired, and attempts not exceeded."""
        return self.consumed_at is None and timezone.now() < self.expires_at and self.attempt_count < self.max_attempts

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def attempts_exceeded(self) -> bool:
        return self.attempt_count >= self.max_attempts

    def consume(self) -> None:
        """Mark this pending authentication as consumed."""
        self.consumed_at = timezone.now()
        self.save(update_fields=["consumed_at", "version", "updated_at"])

    def increment_attempts(self) -> None:
        """Increment the failed MFA attempt counter."""
        self.attempt_count += 1
        self.save(update_fields=["attempt_count", "version", "updated_at"])
