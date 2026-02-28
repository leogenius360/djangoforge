"""
File audit dispatch backend.

Appends JSON-lines records to a rotating log file.  Each record is a
single-line JSON object terminated with a newline, making the files easy
to parse with standard tools (``jq``, ``grep``, ``logrotate``, etc.).

File naming conventions
-----------------------
* ``rotate_daily=False`` (default):  ``audit.json`` (or ``audit.json.gz``)
* ``rotate_daily=True``           :  ``audit_YYYY-MM-DD.json``

Configuration via ``AUDITING["BACKEND_OPTIONS"]["file"]``::

    AUDITING = {
        "BACKENDS": ["file"],
        "BACKEND_OPTIONS": {
            "file": {
                "path": "/var/log/audit",     # directory for log files
                "rotate_daily": True,          # new file per day
                "compress": False,             # gzip the output
            },
        },
    }
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from django.utils import timezone

from apps.auditing.backends.base import AuditBackend, AuditBackendError

logger = logging.getLogger(__name__)


class FileAuditBackend(AuditBackend):
    """
    Append-only JSON-lines file backend.

    Thread-safe for single-process deployments.  For multi-process setups
    use a dedicated logging service (e.g. syslog, fluentbit) and pipe the
    file there instead.
    """

    name = "file"

    def __init__(
        self,
        *,
        path: str | None = None,
        base_path: str | None = None,  # alias for backward compatibility
        format: str = "json",  # noqa: A002
        compress: bool = False,
        rotate_daily: bool = True,
        **_extra: Any,
    ) -> None:
        from apps.auditing.settings import audit_settings

        opts = audit_settings.BACKEND_OPTIONS.get("file", {}) or {}
        resolved_path = path or base_path or opts.get("path", "logs/audit")

        self._base_path = Path(resolved_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

        self._format = format
        self._compress = compress if compress is not None else opts.get("compress", False)
        self._rotate_daily = rotate_daily if rotate_daily is not None else opts.get("rotate_daily", True)

    # ------------------------------------------------------------------
    # AuditBackend interface
    # ------------------------------------------------------------------

    def dispatch(self, event_data: dict[str, Any]) -> None:
        """Append ``event_data`` as a JSON line to the current log file."""
        try:
            self._write_record(event_data)
        except OSError as exc:
            raise AuditBackendError(f"FileAuditBackend failed to write: {exc}") from exc

    def health_check(self) -> dict[str, Any]:
        """Verify that the log directory is writable."""
        probe = self._base_path / ".probe"
        try:
            probe.touch(exist_ok=True)
            probe.unlink()
            return {"backend": self.name, "status": "healthy", "available": True, "path": str(self._base_path)}
        except OSError as exc:
            return {
                "backend": self.name,
                "status": "unhealthy",
                "available": False,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Write / read helpers
    # ------------------------------------------------------------------

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
    ) -> str:
        """
        Create and persist a standalone file audit record.

        Returns a generated entry ID (UUID string) that can be used with
        :meth:`read` to retrieve the record.
        """
        entry_id = str(uuid.uuid4())
        now = timezone.now()
        record: dict[str, Any] = {
            "id": entry_id,
            "content_type_id": content_type_id,
            "object_id": object_id,
            "event_type": event_type,
            "version": object_version,
            "snapshot": current_state,
            "delta": changes,
            "actor_id": user_id,
            "session_id": session_id,
            "comment": comment,
            "created_at": now.isoformat(),
        }
        record["checksum"] = self._compute_record_checksum(record)
        self._write_record(record)
        return entry_id

    def read(self, entry_id: str) -> dict[str, Any] | None:
        """Return the first record in any log file whose ``id`` matches ``entry_id``."""
        for log_file in sorted(self._base_path.glob("audit*.json*")):
            record = self._find_in_file(log_file, entry_id)
            if record is not None:
                return record
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_log_file_path(self) -> Path:
        """Return the path of the current active log file."""
        if self._rotate_daily:
            date_str = timezone.now().strftime("%Y-%m-%d")
            filename = f"audit_{date_str}.json"
        else:
            filename = "audit.json"

        if self._compress:
            filename = f"{filename}.gz"

        return self._base_path / filename

    def _write_record(self, record: dict[str, Any]) -> None:
        """Serialise ``record`` as a JSON line and append to the log file."""
        log_file = self._get_log_file_path()
        line = json.dumps(record, default=str, ensure_ascii=False) + "\n"

        if self._compress:
            with gzip.open(log_file, "at", encoding="utf-8") as fh:
                fh.write(line)
        else:
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(line)

    @staticmethod
    def _compute_record_checksum(record: dict[str, Any]) -> str:
        """SHA-256 of the canonical JSON representation of the record."""
        canonical = json.dumps(record, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _find_in_file(self, log_file: Path, entry_id: str) -> dict[str, Any] | None:
        try:
            with (
                gzip.open(log_file, "rt", encoding="utf-8")
                if str(log_file).endswith(".gz")
                else log_file.open("r", encoding="utf-8")
            ) as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("id") == entry_id:
                            return record
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return None
