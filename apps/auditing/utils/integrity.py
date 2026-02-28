"""
Audit event integrity hashing.

Provides ``IntegrityService`` for computing and verifying tamper-evident
SHA-256/SHA-512 checksums that form a chain across an aggregate's event history.

Chain structure
---------------
Each event's checksum is computed over its own payload **plus** the parent's
checksum::

    checksum(event_n) = SHA256(payload(event_n) + parent_checksum(event_n-1))

This means altering any historical event invalidates all subsequent checksums,
making tampering immediately detectable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HashResult:
    """Result of a hashing operation."""

    digest: str  # hex-encoded checksum
    algorithm: str
    input_size: int


class IntegrityService:
    """
    Compute and verify event chain checksums.

    Parameters
    ----------
    algorithm:
        Hash algorithm.  Defaults to ``AUDITING.INTEGRITY_ALGORITHM``.
    """

    _SUPPORTED = frozenset({"sha256", "sha512"})

    def __init__(self, algorithm: str | None = None) -> None:
        from apps.auditing.settings import audit_settings

        self._algorithm = (algorithm or audit_settings.INTEGRITY_ALGORITHM).lower()
        if self._algorithm not in self._SUPPORTED:
            raise ValueError(
                f"Unsupported integrity algorithm: {self._algorithm!r}. Supported: {sorted(self._SUPPORTED)}."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def algorithm(self) -> str:
        """The hash algorithm name (e.g. ``"sha256"``)."""
        return self._algorithm

    def hash(self, data: dict[str, Any]) -> HashResult:
        """
        Compute a deterministic checksum of ``data``.

        Returns an empty ``HashResult`` when ``data`` is ``None`` or empty.
        """
        if not data:
            return HashResult(digest="", algorithm=self._algorithm, input_size=0)
        raw = self._to_bytes(data)
        digest = hashlib.new(self._algorithm, raw).hexdigest()
        return HashResult(digest=digest, algorithm=self._algorithm, input_size=len(raw))

    def verify(
        self,
        data: dict[str, Any],
        expected_digest: str,
        *,
        raise_on_mismatch: bool = False,
    ) -> bool:
        """
        Return True if the computed checksum matches ``expected_digest``.

        Returns ``True`` when ``expected_digest`` is empty (no hash to verify).
        Raises ``IntegrityVerificationError`` when ``raise_on_mismatch`` is True
        and the check fails.
        """
        if not expected_digest:
            return True
        computed = self.hash(data).digest
        ok = hmac.compare_digest(computed, expected_digest)

        if not ok and raise_on_mismatch:
            from apps.auditing.exceptions import IntegrityVerificationError

            raise IntegrityVerificationError(
                f"State integrity verification failed: computed {computed!r} but expected {expected_digest!r}."
            )

        return ok

    # ------------------------------------------------------------------
    # Convenience aliases used by tests
    # ------------------------------------------------------------------

    def hash_simple(self, data: dict[str, Any]) -> str:
        """Compute a deterministic checksum and return just the hex digest."""
        return self.hash(data).digest

    def compute_batch_hash(self, states: list[dict[str, Any]]) -> HashResult:
        """
        Compute a single checksum over a list of state dicts.

        Useful for verifying sets of events atomically.
        Returns an empty ``HashResult`` for an empty list.
        """
        if not states:
            return HashResult(digest="", algorithm=self._algorithm, input_size=0)
        combined = self._to_bytes({"states": states})
        digest = hashlib.new(self._algorithm, combined).hexdigest()
        return HashResult(digest=digest, algorithm=self._algorithm, input_size=len(combined))

    def hash_event_payload(
        self,
        payload: dict[str, Any],
        *,
        parent_checksum: str = "",
    ) -> HashResult:
        """
        Compute the chained checksum for an event.

        Incorporates ``parent_checksum`` into the hash to form a tamper-evident
        linked chain.  When ``AUDITING.INTEGRITY_ENABLED`` is False, returns an
        empty ``HashResult`` (no checksum stored).
        """
        from apps.auditing.settings import audit_settings

        if not audit_settings.INTEGRITY_ENABLED:
            return HashResult(digest="", algorithm=self._algorithm, input_size=0)

        data = dict(payload)
        if parent_checksum:
            data["_parent_checksum"] = parent_checksum
        return self.hash(data)

    def verify_event_chain(
        self,
        payload: dict[str, Any],
        current_checksum: str,
        parent_checksum: str = "",
        *,
        raise_on_mismatch: bool = False,
    ) -> bool:
        """
        Verify that ``current_checksum`` matches a recomputed checksum.

        Parameters
        ----------
        payload:
            The immutable fields of the event (as returned by
            ``BaseEvent._integrity_payload()``).
        current_checksum:
            The checksum stored on the event record.
        parent_checksum:
            The checksum of the preceding event for this aggregate (may be empty
            for the first event).
        raise_on_mismatch:
            If True, raises ``IntegrityVerificationError`` when the check fails
            instead of returning False.
        """
        from apps.auditing.settings import audit_settings

        if not audit_settings.INTEGRITY_ENABLED or not current_checksum:
            return True

        computed = self.hash_event_payload(payload, parent_checksum=parent_checksum).digest
        ok = hmac.compare_digest(computed, current_checksum)

        if not ok and raise_on_mismatch:
            from apps.auditing.exceptions import IntegrityVerificationError

            raise IntegrityVerificationError(
                f"Event chain verification failed: computed {computed!r} but expected {current_checksum!r}."
            )

        return ok

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _to_bytes(data: dict[str, Any]) -> bytes:
        """Deterministic canonical JSON encoding."""
        return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
