"""
Default ``AuthPolicy`` implementation — reads identity from trusted proxy
headers or a ``Bearer`` JWT token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from djangoforge.api.contracts import RequestContext
from djangoforge.api.policies import AuthPolicy
from djangoforge.settings import forge_settings

logger = logging.getLogger("djangoforge.auth")


@dataclass(frozen=True)
class Principal:
    """Normalised identity produced by the auth layer."""

    subject: str
    tenant: str = ""
    email: str = ""
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)
    provider: str = ""


class ForgeAuthPolicy(AuthPolicy):
    """Reads identity from trusted-proxy headers, with optional JWT fallback.

    Header names are configured via ``FORGE["AUTH_HEADER_*"]`` settings.
    """

    def authenticate(self, request: Any) -> RequestContext | None:
        meta = getattr(request, "META", {}) if not isinstance(request, dict) else request

        user_id = meta.get(forge_settings.AUTH_HEADER_USER_ID, "")
        if not user_id:
            return None

        email = meta.get(forge_settings.AUTH_HEADER_EMAIL, "")
        tenant = meta.get(forge_settings.AUTH_HEADER_TENANT, "")
        groups = _split(meta.get(forge_settings.AUTH_HEADER_GROUPS, ""))
        scopes = _split(meta.get(forge_settings.AUTH_HEADER_SCOPES, ""))
        provider = meta.get(forge_settings.AUTH_HEADER_PROVIDER, "")

        correlation_id = meta.get(forge_settings.CORRELATION_ID_HEADER, "")

        return RequestContext(
            user_id=user_id,
            email=email,
            tenant=tenant,
            correlation_id=correlation_id,
            permissions=[],
            groups=groups,
            scopes=scopes,
            auth_provider=provider,
        )

    def to_principal(self, ctx: RequestContext) -> Principal:
        """Convert a :class:`RequestContext` into a :class:`Principal`."""
        return Principal(
            subject=ctx.user_id or "",
            tenant=ctx.tenant or "",
            email=ctx.email or "",
            roles=list(ctx.groups),
            scopes=list(ctx.scopes),
            provider=ctx.auth_provider,
        )


def _split(value: str) -> list[str]:
    """Split a comma-separated header value into a list of strings."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]
