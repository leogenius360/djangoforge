"""Enumeration types for the auditing subsystem."""

from __future__ import annotations

from django.db import models


class EventType(models.TextChoices):
    """Lifecycle event types for audited model operations."""

    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    RESTORE = "restore", "Restore"
    UNDO = "undo", "Undo"
    REDO = "redo", "Redo"
    BULK_CREATE = "bulk_create", "Bulk Create"
    BULK_UPDATE = "bulk_update", "Bulk Update"
    BULK_DELETE = "bulk_delete", "Bulk Delete"
    BULK_RESTORE = "bulk_restore", "Bulk Restore"
    ARCHIVE = "archive", "Archive"
    UNARCHIVE = "unarchive", "Unarchive"
    MERGE = "merge", "Merge"
    SPLIT = "split", "Split"

    @classmethod
    def deletion_types(cls) -> frozenset[str]:
        """Event types that represent deletion operations."""
        return frozenset({cls.DELETE, cls.BULK_DELETE, cls.ARCHIVE})

    @classmethod
    def compensating_types(cls) -> frozenset[str]:
        """Event types that compensate / reverse a prior operation."""
        return frozenset({cls.UNDO, cls.REDO, cls.RESTORE, cls.BULK_RESTORE, cls.UNARCHIVE})

    @classmethod
    def undoable_types(cls) -> frozenset[str]:
        """Event types that may be reversed via an UNDO event."""
        return frozenset({cls.CREATE, cls.UPDATE, cls.DELETE, cls.BULK_CREATE, cls.BULK_UPDATE, cls.BULK_DELETE})

    @classmethod
    def all_values(cls) -> frozenset[str]:
        return frozenset(member.value for member in cls)


class CompressionAlgorithm(models.TextChoices):
    """Supported snapshot compression algorithms."""

    NONE = "none", "None"
    ZLIB = "zlib", "Zlib"
    GZIP = "gzip", "Gzip"
    BROTLI = "brotli", "Brotli"
