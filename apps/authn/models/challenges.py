"""
Verification token model with HMAC-based token and OTP storage.

Raw tokens and OTP codes are **never** stored in the database.  Only their
HMAC-SHA256 digests are persisted.  Raw values are returned to the caller
at creation time and must be delivered immediately (email, SMS, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteModel

from .enums import TokenPurpose

if TYPE_CHECKING:
    from datetime import timedelta


class VerificationToken(SoftDeleteModel):
    """Verification token for email, phone, password reset, and passwordless flows.

    Security properties:
    - ``token_hash`` stores HMAC-SHA256 of the raw token (never plaintext).
    - ``otp_hash`` stores HMAC-SHA256 of the OTP code (never plaintext).
    - ``attempt_count`` / ``max_attempts`` provides per-token brute-force protection.
    - Creating a new token for the same user+purpose invalidates prior tokens.
    """

    principal = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_tokens",
    )

    purpose = models.CharField(max_length=20, choices=TokenPurpose.choices)

    # HMAC-SHA256 hashes -- raw values NEVER stored
    token_hash = models.CharField(max_length=64, db_index=True)
    otp_hash = models.CharField(max_length=64, blank=True, default="")

    # Per-token brute-force protection
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)

    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    # Audit: which email/phone the token was delivered to
    delivery_target = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "verification_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token_hash"]),
            models.Index(fields=["principal", "purpose"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.purpose} token for {self.principal}"

    @property
    def is_valid(self) -> bool:
        """Token is valid if unused, not expired, and attempts not exceeded."""
        return self.used_at is None and timezone.now() < self.expires_at and self.attempt_count < self.max_attempts

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def attempts_exceeded(self) -> bool:
        return self.attempt_count >= self.max_attempts

    def mark_used(self) -> None:
        """Mark the token as consumed."""
        self.used_at = timezone.now()
        self.save(update_fields=["used_at", "version", "updated_at"])

    def increment_attempts(self) -> None:
        """Increment the attempt counter."""
        self.attempt_count += 1
        self.save(update_fields=["attempt_count", "version", "updated_at"])

    @classmethod
    def invalidate_existing(cls, principal: object, purpose: str) -> int:
        """Soft-delete all unused tokens for the given principal and purpose."""
        return (
            cls.objects.filter(
                principal=principal,
                purpose=purpose,
                used_at__isnull=True,
            )
            .active()
            .delete()
        )

    @classmethod
    def create_for_principal(
        cls,
        *,
        principal: object,
        purpose: str,
        token_hash: str,
        otp_hash: str = "",
        ttl: timedelta,
        max_attempts: int = 5,
        delivery_target: str = "",
    ) -> VerificationToken:
        """Create a new verification token (stores HMAC hashes only).

        Prior unused tokens for the same principal+purpose are invalidated first.
        """
        cls.invalidate_existing(principal, purpose)
        return cls.objects.create(
            principal=principal,
            purpose=purpose,
            token_hash=token_hash,
            otp_hash=otp_hash,
            max_attempts=max_attempts,
            expires_at=timezone.now() + ttl,
            delivery_target=delivery_target,
        )
