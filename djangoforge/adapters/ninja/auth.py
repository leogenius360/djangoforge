"""
Ninja auth backend that delegates to :class:`~djangoforge.auth.ForgeAuthPolicy`.
"""

from __future__ import annotations

from typing import Any

from djangoforge.auth.policy import ForgeAuthPolicy


class ForgeNinjaAuth:
    """Ninja-compatible auth dependency backed by :class:`ForgeAuthPolicy`.

    Usage with Ninja::

        from djangoforge.adapters.ninja import ForgeNinjaAuth
        api = NinjaAPI(auth=ForgeNinjaAuth())
    """

    def __init__(self, policy: ForgeAuthPolicy | None = None) -> None:
        self.policy = policy or ForgeAuthPolicy()

    def __call__(self, request: Any) -> Any:
        ctx = self.policy.authenticate(request)
        if ctx is None:
            return None
        request.forge_context = ctx
        return ctx
