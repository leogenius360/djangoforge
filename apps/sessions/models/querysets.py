from __future__ import annotations

from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import BaseQuerySet


class AuthSessionQuerySet(BaseQuerySet):
    """QuerySet helpers for AuthSession."""

    def for_principal(self, principal):
        """Filter sessions for a specific principal."""
        return self.filter(principal=principal)

    def non_terminal(self):
        """Return sessions that may still transition (not disabled and not deleted)."""
        return self.filter(disabled_at__isnull=True, deleted_at__isnull=True)

    def terminal(self):
        """Return terminal sessions (disabled or deleted)."""
        return self.filter(Q(disabled_at__isnull=False) | Q(deleted_at__isnull=False))

    def valid(self, now=None):
        """
        Return sessions valid for authentication.

        Parameters
        ----------
        now:
            Optional override for deterministic testing.

        Returns
        -------
        QuerySet
            Filtered queryset.
        """
        now = now or timezone.now()
        return (
            self.filter(
                deleted_at__isnull=True,
                disabled_at__isnull=True,
                suspended_at__isnull=True,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .filter(Q(idle_expires_at__isnull=True) | Q(idle_expires_at__gt=now))
            .filter(Q(locked_until__isnull=True) | Q(locked_until__lte=now))
            .filter(
                principal__deleted_at__isnull=True,
                principal__disabled_at__isnull=True,
            )
            .filter(security_stamp_at_issue=F("principal__security_stamp"))
        )

    def due_for_expiry(self, now=None):
        """Return non-terminal sessions whose absolute expiry has passed."""
        now = now or timezone.now()
        return self.non_terminal().filter(expires_at__isnull=False, expires_at__lte=now)

    def due_for_idle_expiry(self, now=None):
        """Return non-terminal sessions whose idle expiry has passed."""
        now = now or timezone.now()
        return self.non_terminal().filter(idle_expires_at__isnull=False, idle_expires_at__lte=now)
