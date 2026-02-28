"""
Django admin registration for the auditing subsystem.

Events are **immutable** once created; the admin is intentionally read-only
(no add, change, or delete permissions).  Staff users can browse, search, and
filter the event log, but cannot modify any record.
"""

from __future__ import annotations

from django.contrib import admin

from apps.auditing.models.event import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    # ------------------------------------------------------------------
    # List view
    # ------------------------------------------------------------------
    list_display = [
        "id_short",
        "event_type",
        "content_type",
        "object_id",
        "version",
        "actor",
        "created_at",
        "has_snapshot",
        "has_changes",
        "is_fully_dispatched",
    ]
    list_filter = ["event_type", "content_type", "created_at", "deleted_at"]
    search_fields = ["object_id", "actor__username", "actor__email", "comment", "checksum"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    # ------------------------------------------------------------------
    # Detail view — all fields are read-only
    # ------------------------------------------------------------------
    readonly_fields = [
        "id",
        "content_type",
        "object_id",
        "event_type",
        "version",
        "actor",
        "snapshot",
        "snapshot_compressed",
        "delta",
        "checksum",
        "parent",
        "parent_checksum",
        "target_event",
        "compression_algorithm",
        "original_size",
        "compressed_size",
        "context",
        "comment",
        "backends_pending",
        "backends_dispatched",
        "backends_failed",
        "deleted_at",
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        (
            "Event",
            {
                "fields": [
                    "id",
                    "event_type",
                    "version",
                    "created_at",
                    "updated_at",
                    "deleted_at",
                ]
            },
        ),
        (
            "Subject",
            {"fields": ["content_type", "object_id"]},
        ),
        (
            "Actor",
            {"fields": ["actor", "context"]},
        ),
        (
            "State",
            {
                "fields": [
                    "snapshot",
                    "snapshot_compressed",
                    "delta",
                    "compression_algorithm",
                    "original_size",
                    "compressed_size",
                ]
            },
        ),
        (
            "Integrity chain",
            {"fields": ["checksum", "parent", "parent_checksum", "target_event"]},
        ),
        (
            "Outbox",
            {"fields": ["backends_pending", "backends_dispatched", "backends_failed"]},
        ),
        (
            "Annotation",
            {"fields": ["comment"]},
        ),
    ]

    # ------------------------------------------------------------------
    # Immutability — no add, change, or delete
    # ------------------------------------------------------------------

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    # ------------------------------------------------------------------
    # Custom list_display columns
    # ------------------------------------------------------------------

    @admin.display(description="ID (short)", ordering="id")
    def id_short(self, obj: Event) -> str:
        """Display the first 8 characters of the UUID."""
        return str(obj.pk)[:8] if obj.pk else "—"

    @admin.display(description="Snapshot?", boolean=True)
    def has_snapshot(self, obj: Event) -> bool:
        return obj.snapshot is not None or obj.snapshot_compressed is not None

    @admin.display(description="Changes?", boolean=True)
    def has_changes(self, obj: Event) -> bool:
        return bool(obj.delta)
