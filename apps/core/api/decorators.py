"""
Decorator stubs for the DjangoForge API layer.

Provides no-op replacements for ``drf_spectacular.utils.extend_schema``
and related decorators so existing call-sites only need an import change.
"""

from __future__ import annotations

from typing import Any


def extend_schema(
    *,
    summary: str | None = None,
    description: str | None = None,
    request: Any = None,
    responses: Any = None,
    parameters: list | None = None,
    tags: list[str] | None = None,
    operation_id: str | None = None,
    **kwargs,
):
    """No-op decorator that replaces ``drf_spectacular.utils.extend_schema``."""

    def decorator(func):
        return func

    return decorator


class OpenApiParameter:
    """Stub for ``drf_spectacular.utils.OpenApiParameter``."""

    QUERY = "query"
    PATH = "path"
    HEADER = "header"
    COOKIE = "cookie"

    def __init__(
        self,
        name: str,
        type: Any = str,
        location: str = QUERY,
        required: bool = False,
        description: str = "",
        **kwargs,
    ):
        self.name = name
        self.type = type
        self.location = location
        self.required = required
        self.description = description
