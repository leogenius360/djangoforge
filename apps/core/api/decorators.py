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


def extend_schema_view(**kwargs):
    """No-op decorator that replaces ``drf_spectacular.utils.extend_schema_view``."""

    def decorator(cls):
        return cls

    return decorator


class OpenApiAuthenticationExtension:
    """Stub for ``drf_spectacular.extensions.OpenApiAuthenticationExtension``."""

    target_class: str = ""
    name: str = ""

    def get_security_definition(self, auto_schema):
        return {}


class OpenApiResponse:
    """Stub for ``drf_spectacular.utils.OpenApiResponse``."""

    def __init__(self, description: str = "", response: Any = None, **kwargs):
        self.description = description
        self.response = response


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
