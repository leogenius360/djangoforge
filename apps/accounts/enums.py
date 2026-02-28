"""
Account-specific enumerations.

Kept in a dedicated module to avoid circular imports and to allow
importing enums without pulling in Django models.
"""

from __future__ import annotations

from django.db.models import TextChoices

from apps.core.enums import CoreStatus


class PrincipalKind(TextChoices):
    """Supported principal categories.

    These values are the built-in kinds.  Additional kinds can be registered
    via ``ACCOUNTS["PRINCIPAL_KINDS"]`` in Django settings.

    Each kind maps to a concrete account model linked via OneToOneField:

    - ``USER``       -> ``UserAccount``
    - ``SERVICE``    -> ``ServiceAccount``
    - ``API_CLIENT`` -> ``APIClient``
    - ``AGENT``      -> ``AgentAccount``
    """

    USER = "user", "User Account"
    SERVICE = "service", "Service Account"
    API_CLIENT = "api_client", "API Client"
    AGENT = "agent", "Agent"


# Re-export CoreStatus under a domain-specific alias for accounts usage.
PrincipalStatus = CoreStatus

__all__ = [
    "PrincipalKind",
    "PrincipalStatus",
]
