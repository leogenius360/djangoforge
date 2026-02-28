"""
Auditing settings loader.

Reads from Django settings::

    AUDITING = {
        "ENABLED": True,
        "AUDITED_APPS": ["accounts"],
        "AUDITED_MODELS": {
            "accounts.UserAccount": {"track_fields": ["email", "status"]},
        },
        "EXCLUDED_MODELS": ["admin.LogEntry"],
        "BACKENDS": ["file"],
        "BACKEND_OPTIONS": {
            "file": {"log_dir": "/var/log/audit", "rotate_mb": 100},
            "redis": {"url": "redis://localhost:6379", "stream_key": "audit:events"},
            "kafka": {"bootstrap_servers": "localhost:9092", "topic": "audit.events"},
        },
        "COMPRESSION_ENABLED": False,
        "COMPRESSION_ALGORITHM": "zlib",
        "COMPRESSION_THRESHOLD": 10240,
        "INTEGRITY_ENABLED": True,
        "INTEGRITY_ALGORITHM": "sha256",
        "SNAPSHOT_ON_CREATE": True,
        "SNAPSHOT_ON_DELETE": True,
        "SNAPSHOT_INTERVAL": 10,
        "TRACK_DELTAS": True,
        "GLOBAL_EXCLUDE_FIELDS": ["password", "token", "secret", "key"],
        "UNDO_ENABLED": True,
        "MAX_UNDO_DEPTH": 10,
        "RETENTION_DAYS": None,
    }

Unknown keys raise ``ImproperlyConfigured`` at startup (strict namespace).
"""

from __future__ import annotations

from typing import Any, ClassVar, Final, TypeVar, get_origin

from django.test.signals import setting_changed

from apps.core.settings import BaseSettings

T = TypeVar("T")


def _is_literal(annotation: Any) -> bool:
    from typing import Literal

    return get_origin(annotation) is Literal


def _type_name(tp: Any) -> str:
    try:
        return tp.__name__
    except AttributeError:
        return str(tp)


class AuditingSettings(BaseSettings):
    """Typed settings for the auditing subsystem."""

    settings_key: ClassVar[str] = "AUDITING"
    strict_namespace: ClassVar[bool] = True

    # Global toggle
    ENABLED: bool = True

    # Model selection
    AUDITED_APPS: list[str] = []
    AUDITED_MODELS: dict[str, Any] = {}
    EXCLUDED_MODELS: list[str] = [
        "auditing.Event",
        "contenttypes.ContentType",
        "auth.Permission",
        "sessions.Session",
        "admin.LogEntry",
    ]

    # Optional additional backends (DB is always on)
    # Supported values: "file", "redis", "kafka"
    BACKENDS: list[str] = []
    BACKEND_OPTIONS: dict[str, Any] = {}

    # Compression
    COMPRESSION_ENABLED: bool = False
    COMPRESSION_ALGORITHM: str = "zlib"  # zlib | gzip | brotli
    COMPRESSION_THRESHOLD: int = 1024  # bytes

    # Integrity hashing
    INTEGRITY_ENABLED: bool = True
    INTEGRITY_ALGORITHM: str = "sha256"  # sha256 | sha512

    # Snapshot strategy
    SNAPSHOT_ON_CREATE: bool = True
    SNAPSHOT_ON_DELETE: bool = True
    SNAPSHOT_INTERVAL: int = 10  # full snapshot every N events (0 = always)

    # Delta tracking
    TRACK_DELTAS: bool = True
    GLOBAL_EXCLUDE_FIELDS: list[str] = ["password", "token", "secret", "key"]

    # Undo/Redo
    UNDO_ENABLED: bool = True
    MAX_UNDO_DEPTH: int = 10

    # Retention (None = indefinite)
    RETENTION_DAYS: int | None = None


audit_settings: Final[AuditingSettings] = AuditingSettings()


def _on_setting_changed(sender: object, setting: str, **_: Any) -> None:
    if audit_settings.is_related_setting(setting):
        audit_settings.reload()


setting_changed.connect(_on_setting_changed)
