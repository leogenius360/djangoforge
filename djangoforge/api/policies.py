"""
Policy hook interfaces for the Forge API contract.

These abstract classes define the extension points that enterprise teams
customize, while Forge adapters call them uniformly.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from djangoforge.api.contracts import RequestContext


class AuthPolicy(abc.ABC):
    """Determines *who* the caller is.

    Concrete implementations read trusted proxy headers, JWT tokens, or any
    other identity source and produce a :class:`RequestContext`.
    """

    @abc.abstractmethod
    def authenticate(self, request: Any) -> RequestContext | None:
        """Return a RequestContext if the request is authenticated, else ``None``."""


class PermissionPolicy(abc.ABC):
    """Determines *what* the caller may do (RBAC / ABAC)."""

    @abc.abstractmethod
    def has_permission(self, context: RequestContext, action: str, resource: str | None = None) -> bool:
        """Return ``True`` if *context* is authorised for *action* on *resource*."""


class RateLimitPolicy(abc.ABC):
    """Per-caller or per-tenant rate limiting."""

    @abc.abstractmethod
    def allow(self, context: RequestContext, action: str) -> bool:
        """Return ``True`` if the request is within the rate limit."""


class IdempotencyPolicy(abc.ABC):
    """Idempotency-key management for safe retries."""

    @abc.abstractmethod
    def is_duplicate(self, idempotency_key: str) -> bool:
        """Return ``True`` if this key has already been processed."""

    @abc.abstractmethod
    def record(self, idempotency_key: str, response: Any) -> None:
        """Store the result for future deduplication lookups."""

    @abc.abstractmethod
    def get_cached_response(self, idempotency_key: str) -> Any | None:
        """Return the previously stored response, or ``None``."""
