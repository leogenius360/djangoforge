"""
Account query helpers.

Provides ``PrincipalQuerySet`` with enterprise-grade filtering for
lifecycle states, principal kinds, and authentication eligibility.

Compliance alignment
--------------------
- ISO 27001 A.9    -- Access control filtering
- NIST 800-63B     -- Authentication eligibility predicates
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.core.models.querysets import SoftDeleteQuerySet


class PrincipalQuerySet(SoftDeleteQuerySet):
    """QuerySet for Principal with principal-specific predicates.

    Inherits from ``SoftDeleteQuerySet`` which provides:
    - ``active()`` -- non-deleted rows
    - ``deleted()`` -- soft-deleted rows
    - ``soft_delete()`` / ``restore()`` / ``hard_delete()``
    - ``update()`` / ``bulk_update()`` with version + updated_at enforcement
    """

    def active(self):
        """Return non-deleted principals (including locked/suspended/disabled).

        For authentication-eligible filtering, use ``authenticatable()`` instead.
        """
        return super().active()

    # ------------------------------------------------------------------
    # Username lookups
    # ------------------------------------------------------------------

    def by_username(self, username: str):
        """Case-insensitive username lookup."""
        return self.filter(username__iexact=username)

    # ------------------------------------------------------------------
    # Kind filters
    # ------------------------------------------------------------------

    def users(self):
        """Return principals of kind USER."""
        return self.filter(kind="user")

    def services(self):
        """Return principals of kind SERVICE."""
        return self.filter(kind="service")

    def api_clients(self):
        """Return principals of kind API_CLIENT."""
        return self.filter(kind="api_client")

    def agents(self):
        """Return principals of kind AGENT."""
        return self.filter(kind="agent")

    def by_kind(self, kind: str):
        """Return principals of a specific kind."""
        return self.filter(kind=kind)

    # ------------------------------------------------------------------
    # Authentication eligibility
    # ------------------------------------------------------------------

    def authenticatable(self):
        """Return principals eligible to authenticate.

        Mirrors ``Principal.can_authenticate`` at the query level:
        - not soft-deleted
        - not currently locked (locked_until in the past or null)
        - not suspended
        - not disabled
        - not expired

        Compliance: NIST 800-63B s7.1 -- session binding.
        """
        now = timezone.now()
        return (
            super()
            .active()
            .filter(
                suspended_at__isnull=True,
                disabled_at__isnull=True,
            )
            .filter(Q(locked_until__isnull=True) | Q(locked_until__lte=now))
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        )

    # ------------------------------------------------------------------
    # Eager loading
    # ------------------------------------------------------------------

    def with_concrete(self):
        """Eagerly load all concrete OneToOne relations.

        Useful when you need to display principal + concrete type info
        without N+1 queries.
        """
        return self.select_related(
            "user_account",
            "service_account",
            "api_client",
            "agent_account",
        )
