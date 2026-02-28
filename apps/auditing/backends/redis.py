"""
Redis audit dispatch backend.

Publishes ``Event`` records to a **Redis Stream** using the ``XADD`` command.
Redis Streams are append-only, consumer-group aware, and support message
acknowledgement — making them an excellent fit for the audit outbox pattern.

Configuration via ``AUDITING["BACKEND_OPTIONS"]["redis"]``::

    AUDITING = {
        "BACKENDS": ["redis"],
        "BACKEND_OPTIONS": {
            "redis": {
                "url": "redis://localhost:6379/0",
                "stream_key": "audit:events",
                "maxlen": 1_000_000,   # approximate MAXLEN for pruning
            },
        },
    }

Requires the ``redis`` package (already listed in ``requirements/base.txt``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from apps.auditing.backends.base import AuditBackend, AuditBackendError, AuditBackendUnavailableError

logger = logging.getLogger(__name__)


class RedisAuditBackend(AuditBackend):
    """
    Redis Streams dispatch backend.

    Each dispatched event is added as a stream entry (XADD).  Consumers
    can use consumer groups to process events at-least-once.
    """

    name = "redis"

    def __init__(
        self,
        *,
        url: str | None = None,
        stream_key: str | None = None,
        maxlen: int = 1_000_000,
        **_extra: Any,
    ) -> None:
        from apps.auditing.settings import audit_settings

        opts: dict[str, Any] = audit_settings.BACKEND_OPTIONS.get("redis", {}) or {}
        self._url = url or opts.get("url", "redis://localhost:6379/0")
        self._stream_key = stream_key or opts.get("stream_key", "audit:events")
        self._maxlen = maxlen or opts.get("maxlen", 1_000_000)
        self._client: Any = None
        self._connect()

    # ------------------------------------------------------------------
    # AuditBackend interface
    # ------------------------------------------------------------------

    def dispatch(self, event_data: dict[str, Any]) -> None:
        """Publish ``event_data`` to the Redis stream (XADD)."""
        if self._client is None:
            raise AuditBackendUnavailableError(self.name, "Redis client not connected")

        try:
            # Redis stream entries require string values
            fields = {
                k: json.dumps(v, default=str) if not isinstance(v, (str, bytes)) else v for k, v in event_data.items()
            }
            self._client.xadd(self._stream_key, fields, maxlen=self._maxlen, approximate=True)
        except Exception as exc:
            raise AuditBackendError(f"RedisAuditBackend dispatch failed: {exc}") from exc

    def health_check(self) -> dict[str, Any]:
        """Ping Redis and return health status."""
        if self._client is None:
            return {
                "backend": self.name,
                "status": "unhealthy",
                "available": False,
                "error": "Redis client not initialised",
            }
        try:
            self._client.ping()
            stream_len = self._client.xlen(self._stream_key) if self._client.exists(self._stream_key) else 0
            return {
                "backend": self.name,
                "status": "healthy",
                "available": True,
                "stream_key": self._stream_key,
                "stream_length": stream_len,
            }
        except Exception as exc:
            return {
                "backend": self.name,
                "status": "unhealthy",
                "available": False,
                "error": str(exc),
            }

    def is_available(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        try:
            import redis  # type: ignore[import-untyped]

            self._client: redis.Redis = redis.from_url(self._url, decode_responses=True)
            self._client.ping()
            logger.info("RedisAuditBackend: connected to %s (stream=%s)", self._url, self._stream_key)
        except ImportError:
            logger.warning("RedisAuditBackend: 'redis' package not installed — backend disabled.")
            self._client = None
        except Exception as exc:
            logger.warning("RedisAuditBackend: connection failed (%s) — backend disabled.", exc)
            self._client = None
