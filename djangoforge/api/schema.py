"""
Schema hooks — OpenAPI metadata, versioning and deprecation registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EndpointMeta:
    """Metadata for a single API endpoint."""

    operation_id: str = ""
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    deprecated: bool = False
    version: str = "v1"
    auth_required: bool = True
    responses: dict[int, str] = field(default_factory=dict)


class SchemaRegistry:
    """Collects OpenAPI metadata across the project.

    Adapters register endpoint metadata here; ``forge check`` reads it.
    """

    def __init__(self) -> None:
        self._endpoints: dict[str, EndpointMeta] = {}

    def register(self, path: str, meta: EndpointMeta) -> None:
        self._endpoints[path] = meta

    def get(self, path: str) -> EndpointMeta | None:
        return self._endpoints.get(path)

    def all(self) -> dict[str, EndpointMeta]:
        return dict(self._endpoints)

    def validate(self) -> list[str]:
        """Return a list of validation errors for registered endpoints."""
        from djangoforge.settings import forge_settings

        issues: list[str] = []
        for path, meta in self._endpoints.items():
            if forge_settings.OPENAPI_REQUIRE_OPERATION_ID and not meta.operation_id:
                issues.append(f"{path}: missing operationId")
            if forge_settings.OPENAPI_REQUIRE_TAGS and not meta.tags:
                issues.append(f"{path}: missing tags")
            if forge_settings.OPENAPI_REQUIRE_RESPONSES and not meta.responses:
                issues.append(f"{path}: missing responses")
        return issues


# Module-level singleton for convenience.
schema_registry = SchemaRegistry()


def openapi_meta(
    path: str,
    *,
    operation_id: str = "",
    tags: list[str] | None = None,
    summary: str = "",
    deprecated: bool = False,
    version: str = "v1",
    auth_required: bool = True,
    responses: dict[int, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> EndpointMeta:
    """Helper to register and return endpoint metadata in one call."""
    meta = EndpointMeta(
        operation_id=operation_id,
        tags=tags or [],
        summary=summary,
        deprecated=deprecated,
        version=version,
        auth_required=auth_required,
        responses=responses or {},
    )
    schema_registry.register(path, meta)
    return meta
