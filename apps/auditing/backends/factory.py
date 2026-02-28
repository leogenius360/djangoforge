"""
Backend factory and registry.

Use :func:`get_audit_backend` to obtain a backend instance by name and
:func:`get_configured_backends` to instantiate all backends listed in
``AUDITING["BACKENDS"]`` using ``AUDITING["BACKEND_OPTIONS"]``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.auditing.backends.base import AuditBackend

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------


def _backend_registry() -> dict[str, type[AuditBackend]]:
    """Lazy import registry to avoid circular imports at module load time."""
    from apps.auditing.backends.file import FileAuditBackend
    from apps.auditing.backends.kafka import KafkaAuditBackend
    from apps.auditing.backends.redis import RedisAuditBackend

    return {
        "file": FileAuditBackend,
        "redis": RedisAuditBackend,
        "kafka": KafkaAuditBackend,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_audit_backend(name: str, **options: Any) -> AuditBackend:
    """
    Instantiate a backend by name.

    Parameters
    ----------
    name:
        Backend identifier, e.g. ``"file"``, ``"redis"``, ``"kafka"``.
    **options:
        Keyword arguments forwarded to the backend constructor.  These take
        precedence over any matching keys in ``AUDITING["BACKEND_OPTIONS"]``.

    Raises
    ------
    ValueError
        When ``name`` is not a registered backend identifier.
    """
    registry = _backend_registry()
    backend_cls = registry.get(name)
    if backend_cls is None:
        known = ", ".join(sorted(registry))
        raise ValueError(f"Unknown audit backend: {name!r}. Known backends: {known}.")
    return backend_cls(**options)


def get_configured_backends() -> list[AuditBackend]:
    """
    Instantiate all backends declared in ``AUDITING["BACKENDS"]``.

    Each backend is initialised with the matching sub-dict from
    ``AUDITING["BACKEND_OPTIONS"]``.  Unavailable backends (e.g. Kafka not
    reachable) are skipped with a warning rather than crashing startup.
    """
    from apps.auditing.settings import audit_settings

    backends: list[AuditBackend] = []
    for backend_name in audit_settings.BACKENDS:
        opts: dict[str, Any] = audit_settings.BACKEND_OPTIONS.get(backend_name, {}) or {}
        try:
            backend = get_audit_backend(backend_name, **opts)
            backends.append(backend)
        except ValueError:
            logger.warning("AUDITING.BACKENDS: unknown backend %r — skipping.", backend_name)
        except Exception as exc:
            logger.error("AUDITING.BACKENDS: failed to initialise %r: %s", backend_name, exc)
    return backends


# Alias for backward compatibility
get_all_backends = get_configured_backends
