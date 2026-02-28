"""
Forge router factory for Django Ninja.

Usage::

    from djangoforge.adapters.ninja import forge_router

    router = forge_router(tags=["billing"])

    @router.get("/invoices")
    def list_invoices(request):
        ...
"""

from __future__ import annotations

from typing import Any


def forge_router(*, tags: list[str] | None = None, **kwargs: Any) -> Any:
    """Create a Ninja ``Router`` pre-configured with Forge defaults.

    Raises ``ImportError`` if ``ninja`` is not installed.
    """
    try:
        from ninja import Router
    except ImportError as exc:
        raise ImportError(
            "django-ninja is required for the Ninja adapter. Install it with: pip install django-ninja"
        ) from exc

    return Router(tags=tags or [], **kwargs)
