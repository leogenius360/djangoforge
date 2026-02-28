"""
Login attempt tracking model.

Persisted for audit trail and lockout decisions.  ``LoginAttempt`` records
are immutable (no soft delete) and use ``BaseModel`` for UUID PK, timestamps,
and version control.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel

from .enums import LoginAttemptResult


class LoginAttemptQuerySet(models.QuerySet):
    """QuerySet helpers for login attempt analysis."""

    def recent(self, minutes: int = 30) -> LoginAttemptQuerySet:
        """Attempts within the last *minutes*."""
        cutoff = timezone.now() - timezone.timedelta(minutes=minutes)
        return self.filter(created_at__gte=cutoff)

    def for_principal(self, principal: object) -> LoginAttemptQuerySet:
        return self.filter(principal=principal)

    def for_ip(self, ip_address: str) -> LoginAttemptQuerySet:
        return self.filter(ip_address=ip_address)

    def failures(self) -> LoginAttemptQuerySet:
        return self.exclude(result=LoginAttemptResult.SUCCESS)

    def successes(self) -> LoginAttemptQuerySet:
        return self.filter(result=LoginAttemptResult.SUCCESS)


class LoginAttemptManager(models.Manager.from_queryset(LoginAttemptQuerySet)):
    """Manager for ``LoginAttempt`` with convenience methods."""

    def recent_failures(self, principal: object, window_minutes: int = 30) -> LoginAttemptQuerySet:
        """Failed login attempts for *principal* within the time window."""
        return self.for_principal(principal).recent(window_minutes).failures()

    def failure_count(self, principal: object, window_minutes: int = 30) -> int:
        """Count of failed login attempts for *principal* within the time window."""
        return self.recent_failures(principal, window_minutes).count()

    def recent_lockouts(self, principal: object, window_hours: int = 24) -> LoginAttemptQuerySet:
        """Account-locked attempts for *principal* within the time window."""
        cutoff = timezone.now() - timezone.timedelta(hours=window_hours)
        return self.for_principal(principal).filter(
            result=LoginAttemptResult.ACCOUNT_LOCKED,
            created_at__gte=cutoff,
        )


class LoginAttempt(BaseModel):
    """Persisted login attempt record for audit and lockout decisions.

    Uses ``BaseModel`` (UUID PK, timestamps, version) -- NOT soft-deletable
    because audit records are immutable.
    """

    principal = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_attempts",
    )
    identifier = models.CharField(
        max_length=255,
        db_index=True,
        help_text="The identifier used (email, username, phone number).",
    )

    result = models.CharField(
        max_length=30,
        choices=LoginAttemptResult.choices,
        db_index=True,
    )
    auth_method = models.CharField(max_length=30, blank=True, default="")

    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")

    failure_reason = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    objects = LoginAttemptManager()

    class Meta:
        db_table = "login_attempts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["principal", "result", "created_at"]),
            models.Index(fields=["identifier", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.result} attempt for {self.identifier} at {self.created_at}"
