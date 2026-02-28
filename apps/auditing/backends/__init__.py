"""
Audit dispatch backends package.

Backends forward ``Event`` records written by the outbox to external systems
(append-only files, Redis streams, Kafka topics, etc.).  The database is
always the primary store — these backends are optional secondary sinks.

Supported backend identifiers (used in ``AUDITING["BACKENDS"]``):
* ``"file"``  — append JSON lines to a rotating log file
* ``"redis"`` — publish to a Redis stream (XADD)
* ``"kafka"`` — produce to a Kafka topic

Configuration example::

    AUDITING = {
        "BACKENDS": ["file", "redis"],
        "BACKEND_OPTIONS": {
            "file": {"path": "/var/log/audit", "rotate_daily": True, "compress": False},
            "redis": {"url": "redis://localhost:6379", "stream_key": "audit:events"},
        },
    }
"""

from apps.auditing.backends.base import AuditBackend, AuditBackendError, AuditBackendUnavailableError
from apps.auditing.backends.factory import get_audit_backend, get_configured_backends

__all__ = [
    "AuditBackend",
    "AuditBackendError",
    "AuditBackendUnavailableError",
    "get_audit_backend",
    "get_configured_backends",
]
