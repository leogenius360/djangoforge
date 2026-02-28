"""
Multi-backend coordinator.

The coordinator dispatches a single audit event to multiple registered
backends in sequence.  It operates in one of two modes:

* ``strict_mode=True``  — raises ``RuntimeError`` if **any** backend fails;
  the caller is expected to roll back or retry.
* ``strict_mode=False`` (default) — "best-effort": continues after failures
  and returns a result dict that summarises per-backend outcomes.

The coordinator uses :func:`~apps.auditing.backends.factory.get_all_backends`
to obtain the backends list unless you pass ``backends`` explicitly.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MultiBackendCoordinator:
    """
    Dispatch an audit event to multiple backends in sequence.

    Parameters
    ----------
    strict_mode:
        When True, any backend failure raises RuntimeError.  When False
        (default), failures are collected and returned in the result dict.
    backends:
        Optional explicit list of :class:`~apps.auditing.backends.base.AuditBackend`
        instances.  When ``None`` the configured backends are loaded via
        :func:`~apps.auditing.backends.factory.get_all_backends`.
    """

    def __init__(
        self,
        *,
        strict_mode: bool = False,
        backends: list[Any] | None = None,
    ) -> None:
        self._strict = strict_mode
        if backends is not None:
            self._backends = backends
        else:
            from apps.auditing.backends.factory import get_all_backends

            self._backends = get_all_backends()

    # ------------------------------------------------------------------
    # Dispatch interface
    # ------------------------------------------------------------------

    def dispatch(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """
        Forward ``event_data`` to all registered backends.

        Returns a result dict::

            {
                "success": bool,        # True when all backends succeeded
                "results": {
                    "<backend_name>": {
                        "ok": bool,
                        "error": str | None,
                    },
                },
            }
        """
        results: dict[str, Any] = {}
        all_ok = True

        for backend in self._backends:
            try:
                backend.dispatch(event_data)
                results[backend.name] = {"ok": True, "error": None}
            except Exception as exc:
                results[backend.name] = {"ok": False, "error": str(exc)}
                all_ok = False
                logger.error("Coordinator: backend %r failed during dispatch: %s", backend.name, exc)
                if self._strict:
                    raise RuntimeError(f"Audit backend {backend.name!r} failed: {exc}") from exc

        return {"success": all_ok, "results": results}

    def write(
        self,
        *,
        content_type_id: int,
        object_id: str,
        event_type: str,
        current_state: dict[str, Any],
        changes: dict[str, Any],
        user_id: str | None,
        session_id: str | None,
        comment: str,
        object_version: int,
    ) -> dict[str, Any]:
        """
        Write an audit record via all backends and aggregate results.

        This is a compatibility method that maps to each backend's ``write()``
        method where available, or falls back to :meth:`dispatch`.

        Returns a result dict::

            {
                "success": bool,
                "primary_entry_id": str | None,
                "results": {
                    "<backend_name>": {
                        "ok": bool,
                        "entry_id": str | None,
                        "error": str | None,
                    },
                },
            }
        """
        kwargs: dict[str, Any] = {
            "content_type_id": content_type_id,
            "object_id": object_id,
            "event_type": event_type,
            "current_state": current_state,
            "changes": changes,
            "user_id": user_id,
            "session_id": session_id,
            "comment": comment,
            "object_version": object_version,
        }
        results: dict[str, Any] = {}
        all_ok = True
        primary_entry_id: str | None = None

        for backend in self._backends:
            write_fn = getattr(backend, "write", None)
            try:
                if callable(write_fn):
                    entry_id = write_fn(**kwargs)
                    results[backend.name] = {"ok": True, "entry_id": str(entry_id), "error": None}
                    if primary_entry_id is None:
                        primary_entry_id = str(entry_id)
                else:
                    # Dispatch-only backend
                    backend.dispatch(kwargs)
                    results[backend.name] = {"ok": True, "entry_id": None, "error": None}
            except Exception as exc:
                results[backend.name] = {"ok": False, "entry_id": None, "error": str(exc)}
                all_ok = False
                logger.error("Coordinator: backend %r write failed: %s", backend.name, exc)
                if self._strict:
                    raise RuntimeError(f"Audit backend {backend.name!r} failed: {exc}") from exc

        return {"success": all_ok, "primary_entry_id": primary_entry_id, "results": results}

    def health_check(self) -> dict[str, Any]:
        """Aggregate health status from all backends."""
        backend_statuses: dict[str, Any] = {}
        for backend in self._backends:
            try:
                status = backend.health_check()
            except Exception as exc:
                status = {"backend": backend.name, "status": "unhealthy", "available": False, "error": str(exc)}
            backend_statuses[backend.name] = status

        healthy = all(s.get("available", False) for s in backend_statuses.values())
        return {
            "healthy": healthy,
            "backends": backend_statuses,
        }
