"""
DRF authentication class backed by :class:`~djangoforge.auth.ForgeAuthPolicy`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework.authentication import BaseAuthentication

from djangoforge.auth.policy import ForgeAuthPolicy

if TYPE_CHECKING:
    from rest_framework.request import Request


class _ForgePrincipalUser:
    """Lightweight user-like wrapper around a :class:`RequestContext`."""

    is_authenticated = True

    def __init__(self, context: Any) -> None:
        self.context = context
        self.pk = context.user_id
        self.username = context.email or context.user_id

    def __str__(self) -> str:
        return self.username or ""


class ForgeAuthentication(BaseAuthentication):
    """DRF ``authentication_classes`` entry that delegates to :class:`ForgeAuthPolicy`."""

    def __init__(self, policy: ForgeAuthPolicy | None = None) -> None:
        self.policy = policy or ForgeAuthPolicy()

    def authenticate(self, request: Request) -> tuple[_ForgePrincipalUser, None] | None:
        ctx = self.policy.authenticate(request._request)  # type: ignore[arg-type]
        if ctx is None:
            return None
        return (_ForgePrincipalUser(ctx), None)
