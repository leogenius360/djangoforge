"""Exception hierarchy for the auditing subsystem."""

from __future__ import annotations

from typing import Any


class AuditError(Exception):
    """Base class for all auditing exceptions."""


class ImmutabilityError(AuditError):
    """Raised when an attempt is made to mutate an immutable audit event field."""

    def __init__(
        self,
        forbidden_fields: set[str] | frozenset[str],
        allowed_fields: set[str] | frozenset[str],
    ) -> None:
        self.forbidden_fields: frozenset[str] = frozenset(forbidden_fields)
        self.allowed_fields: frozenset[str] = frozenset(allowed_fields)
        super().__init__(
            f"Immutable event fields cannot be changed after creation. "
            f"Forbidden: {sorted(self.forbidden_fields)}. "
            f"Mutable: {sorted(self.allowed_fields)}."
        )


class HardDeleteForbiddenError(AuditError):
    """Raised when a hard-delete is attempted outside of an explicitly permitted path."""

    def __init__(self, model_label: str) -> None:
        self.model_label = model_label
        super().__init__(
            f"Hard delete of {model_label!r} audit events is forbidden. "
            "Use soft-delete (QuerySet.delete()) or an explicit GDPR purge routine."
        )


class CompressionError(AuditError):
    """Raised when snapshot compression or decompression fails."""


class CompressionConfigError(CompressionError):
    """Raised when the compression configuration is invalid."""


class IntegrityError(AuditError):
    """Raised when a computed checksum does not match the stored checksum."""

    def __init__(self, expected: str, computed: str) -> None:
        self.expected = expected
        self.computed = computed
        super().__init__(
            f"Audit event integrity check failed. "
            f"Expected checksum {expected!r} but computed {computed!r}. "
            "The event record may have been tampered with."
        )


class SnapshotReconstructionError(AuditError):
    """Raised when state reconstruction from deltas fails."""

    def __init__(self, event_id: Any, reason: str) -> None:
        self.event_id = event_id
        self.reason = reason
        super().__init__(f"Cannot reconstruct state for event {event_id}: {reason}")


class IntegrityVerificationError(IntegrityError):
    """Raised when integrity or chain verification fails (human-readable message variant)."""

    def __init__(self, message: str) -> None:
        Exception.__init__(self, message)


class UndoNotAllowedError(AuditError):
    """Raised when an undo operation cannot be performed on the given event."""


class RedoNotAllowedError(AuditError):
    """Raised when a redo operation cannot be performed on the given event."""


class BackendError(AuditError):
    """Base class for backend-related exceptions."""


class BackendDispatchError(BackendError):
    """Raised when dispatching an event to a backend fails."""
