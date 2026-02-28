"""
Core contract types for the Forge API.

These dataclasses define the shared vocabulary across DRF and Ninja adapters.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestContext:
    """Normalized request identity and metadata.

    Populated by the auth layer and available to every view.
    """

    user_id: str | None = None
    email: str | None = None
    tenant: str | None = None
    correlation_id: str = ""
    auth_claims: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    auth_provider: str = ""


@dataclass
class ProblemDetail:
    """RFC 9457 Problem Details envelope for API errors.

    Every Forge adapter maps exceptions to this shape so consumers see a
    single, predictable error format.
    """

    type: str = "about:blank"
    title: str = "An error occurred"
    status: int = 500
    detail: str = ""
    instance: str = ""
    errors: list[dict[str, Any]] = field(default_factory=list)
    correlation_id: str = ""


@dataclass(frozen=True)
class PaginationSpec:
    """Pagination parameters extracted from the request."""

    page: int = 1
    page_size: int = 20
    cursor: str | None = None


@dataclass(frozen=True)
class FilterSpec:
    """Generic filter specification."""

    field: str = ""
    operator: str = "eq"
    value: Any = None


@dataclass(frozen=True)
class SortSpec:
    """Sort specification."""

    field: str = ""
    direction: str = "asc"


@dataclass
class ApiResponse[T]:
    """Optional wrapper for consistent response shapes."""

    data: T | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    errors: list[ProblemDetail] = field(default_factory=list)
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0
