"""
Abstract audit dispatch backend.

Every concrete backend must implement:

* :attr:`name`             — unique string identifier
* :meth:`dispatch`         — forward a single event payload to the sink
* :meth:`health_check`     — return ``{"status": str, "available": bool, ...}``

Backends receive event data as plain ``dict`` objects (pre-serialized by the
service layer) so that each backend is isolated from Django ORM details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.auditing.models.base import BaseEvent


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuditBackendError(Exception):
    """Base class for backend exceptions."""


class AuditBackendUnavailableError(AuditBackendError):
    """Raised when a backend cannot be contacted or has not been configured."""

    def __init__(self, backend_name: str, reason: str = "") -> None:
        self.backend_name = backend_name
        msg = f"Audit backend {backend_name!r} is unavailable."
        if reason:
            msg = f"{msg} Reason: {reason}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class AuditBackend(ABC):
    """
    Abstract dispatch backend for the audit outbox pattern.

    Subclasses forward ``Event`` records (serialised as ``dict``) to an
    external sink such as a log file, Redis stream, or Kafka topic.
    """

    # Subclasses must declare a unique identifier.
    name: str = "<abstract>"

    # ------------------------------------------------------------------
    # Core interface (mandatory)
    # ------------------------------------------------------------------

    @abstractmethod
    def dispatch(self, event_data: dict[str, Any]) -> None:
        """
        Forward ``event_data`` to the backend sink.

        ``event_data`` is a JSON-serialisable ``dict`` as produced by
        :meth:`serialize_event`.  Implementors should raise
        :exc:`AuditBackendError` on failure so the outbox can track retries.
        """

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """
        Return a health status dict.

        Required keys:
        * ``"backend"``   — the :attr:`name` string
        * ``"status"``    — ``"healthy"`` or ``"unhealthy"``
        * ``"available"`` — ``bool``
        """

    # ------------------------------------------------------------------
    # Helpers (optional override)
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True when the backend is ready to accept events."""
        return True

    def serialize_event(self, event: BaseEvent) -> dict[str, Any]:
        """
        Serialise an ``Event`` Django model instance to a plain ``dict``.

        Override to customise which fields are included in the payload.
        """
        snapshot = event.get_snapshot()
        data: dict[str, Any] = {
            "id": str(event.pk),
            "event_type": event.event_type,
            "version": event.version,
            "content_type_id": event.content_type_id,
            "object_id": event.object_id,
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "checksum": event.checksum,
            "parent_checksum": event.parent_checksum,
            "delta": event.delta,
            "context": event.context or {},
            "comment": event.comment or "",
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        if snapshot is not None:
            data["snapshot"] = snapshot
        return data

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
