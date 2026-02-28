"""
Snapshot compression utilities.

Provides ``CompressionService`` for compressing/decompressing model state
snapshots.  The service respects ``AUDITING.COMPRESSION_ENABLED`` and
``AUDITING.COMPRESSION_ALGORITHM`` settings.

Storage convention
------------------
Compressed snapshots are stored in ``BaseEvent.snapshot_compressed``
(a ``BinaryField``) alongside ``BaseEvent.compression_algorithm``.
The plain-JSON ``snapshot`` field is ``None`` when compressed storage is
active.  ``BaseEvent.get_snapshot()`` decompresses transparently.
"""

from __future__ import annotations

import base64
import gzip as _gzip
import io
import json
import zlib as _zlib
from dataclasses import dataclass
from typing import Any

from apps.auditing.exceptions import CompressionConfigError, CompressionError

# Valid compression level ranges per algorithm
_LEVEL_RANGES: dict[str, tuple[int, int]] = {
    "zlib": (0, 9),
    "gzip": (0, 9),
    "brotli": (0, 11),
}

_DEFAULT_LEVEL = 6


@dataclass(frozen=True)
class CompressionResult:
    """Result of a compression operation."""

    compressed_data: bytes
    algorithm: str
    original_size: int
    compressed_size: int

    @property
    def ratio(self) -> float:
        """Compression ratio (0.0 – 1.0, lower is better)."""
        if self.original_size == 0:
            return 0.0
        return self.compressed_size / self.original_size

    @property
    def compression_ratio(self) -> float:
        """Compression ratio (0.0 – 1.0, lower is better). Alias for ``ratio``."""
        return self.ratio

    @property
    def size_reduction_percent(self) -> float:
        """Percentage size reduction achieved (0–100, higher is better)."""
        if self.original_size == 0:
            return 0.0
        return (1.0 - self.ratio) * 100.0


class CompressionService:
    """
    Compress and decompress model state snapshots.

    Parameters
    ----------
    algorithm:
        Override algorithm.  Defaults to ``AUDITING.COMPRESSION_ALGORITHM``.
    level:
        Compression level (0-9 for zlib/gzip, 0-11 for brotli).
        ``None`` uses the library default (6 for zlib/gzip).
    threshold:
        Minimum byte size to compress.  Defaults to
        ``AUDITING.COMPRESSION_THRESHOLD``.
    """

    _SUPPORTED = frozenset({"none", "zlib", "gzip", "brotli"})

    def __init__(
        self,
        algorithm: str | None = None,
        level: int | None = None,
        threshold: int | None = None,
    ) -> None:
        from apps.auditing.settings import audit_settings

        self._algorithm = (algorithm or audit_settings.COMPRESSION_ALGORITHM).lower()
        self._threshold = threshold if threshold is not None else audit_settings.COMPRESSION_THRESHOLD

        if self._algorithm not in self._SUPPORTED:
            raise CompressionError(
                f"Invalid compression algorithm: {self._algorithm!r}. Supported: {sorted(self._SUPPORTED)}."
            )

        # Resolve and validate level
        if level is None:
            self._level = _DEFAULT_LEVEL if self._algorithm in _LEVEL_RANGES else 0
        else:
            if self._algorithm in _LEVEL_RANGES:
                lo, hi = _LEVEL_RANGES[self._algorithm]
                if not (lo <= level <= hi):
                    raise CompressionError(
                        f"Invalid compression level {level!r} for {self._algorithm!r}. Must be between {lo} and {hi}."
                    )
            self._level = level

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def algorithm(self) -> str:
        """The compression algorithm name (e.g. ``"zlib"``)."""
        return self._algorithm

    @property
    def level(self) -> int:
        """The compression level."""
        return self._level

    @property
    def threshold(self) -> int:
        """Minimum byte size threshold before compression is applied."""
        return self._threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_compress(self, data: dict[str, Any] | None) -> bool:
        """Return True if ``data`` should be compressed."""
        from apps.auditing.settings import audit_settings

        if not audit_settings.COMPRESSION_ENABLED:
            return False
        if self._algorithm == "none":
            return False
        if not data:
            return False
        return len(self._to_bytes(data)) > self._threshold

    def compress(self, data: dict[str, Any], algorithm: str | None = None) -> CompressionResult:
        """Compress ``data`` to bytes.  Raises ``CompressionError`` on failure."""
        if not data:
            raise CompressionError("Cannot compress empty data.")

        raw = self._to_bytes(data)
        original_size = len(raw)

        algo = algorithm or self._algorithm
        if algo == "none":
            return CompressionResult(
                compressed_data=raw,
                algorithm=algo,
                original_size=original_size,
                compressed_size=original_size,
            )

        try:
            compressed = self._compress_bytes(raw, algorithm=algo)
        except CompressionError:
            raise
        except Exception as exc:
            raise CompressionError(f"Compression failed ({algo}): {exc}") from exc
        return CompressionResult(
            compressed_data=compressed,
            algorithm=algo,
            original_size=original_size,
            compressed_size=len(compressed),
        )

    def decompress(self, data: bytes, algorithm: str | None = None) -> dict[str, Any]:
        """Decompress ``data`` back to a dict.  Raises ``CompressionError`` on failure."""
        if not data:
            raise CompressionError("Cannot decompress empty data.")

        algo = algorithm or self._algorithm
        try:
            raw = self._decompress_bytes(data, algorithm=algo)
            return json.loads(raw.decode("utf-8"))
        except CompressionError:
            raise
        except Exception as exc:
            raise CompressionError(f"Decompression failed ({algo}): {exc}") from exc

    def compress_and_encode(self, data: dict[str, Any], algorithm: str | None = None) -> tuple[str, CompressionResult]:
        """
        Compress ``data`` and return a base64-encoded string suitable for JSON storage.

        Returns a tuple of ``(encoded_string, CompressionResult)``.
        """
        result = self.compress(data, algorithm=algorithm)
        encoded = base64.b64encode(result.compressed_data).decode("ascii")
        return encoded, result

    def decode_and_decompress(self, encoded: str, algorithm: str | None = None) -> dict[str, Any]:
        """
        Decode a base64-encoded string and decompress it back to a dict.

        Inverse of ``compress_and_encode``.
        """
        raw = base64.b64decode(encoded.encode("ascii"))
        return self.decompress(raw, algorithm=algorithm)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_bytes(data: dict[str, Any]) -> bytes:
        """Deterministic canonical JSON serialisation."""
        return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")

    def _compress_bytes(self, raw: bytes, algorithm: str | None = None) -> bytes:
        algo = algorithm or self._algorithm
        if algo == "zlib":
            return _zlib.compress(raw, self._level)
        if algo == "gzip":
            buf = io.BytesIO()
            with _gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=self._level) as gz:
                gz.write(raw)
            return buf.getvalue()
        if algo == "brotli":
            try:
                import brotli  # type: ignore[import-untyped]
            except ImportError as exc:
                raise CompressionConfigError("brotli package is not installed.") from exc
            return brotli.compress(raw, quality=self._level)
        raise CompressionConfigError(f"Unsupported compression algorithm: {algo!r}")

    def _decompress_bytes(self, data: bytes, algorithm: str | None = None) -> bytes:
        algo = algorithm or self._algorithm
        if algo in {"none", "zlib"}:
            if algo == "none":
                return data
            return _zlib.decompress(data)
        if algo == "gzip":
            with _gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gz:
                return gz.read()
        if algo == "brotli":
            try:
                import brotli  # type: ignore[import-untyped]
            except ImportError as exc:
                raise CompressionConfigError("brotli package is not installed.") from exc
            return brotli.decompress(data)
        raise CompressionConfigError(f"Unsupported compression algorithm: {algo!r}")

    @staticmethod
    def decompress_with_algorithm(data: bytes, algorithm: str) -> dict[str, Any]:
        """Convenience classmethod-style helper for decompression with an explicit algorithm."""
        svc = CompressionService(algorithm=algorithm)
        return svc.decompress(data)
