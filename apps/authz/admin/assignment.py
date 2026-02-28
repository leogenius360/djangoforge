"""Role assignment admin configuration."""

from __future__ import annotations

from django.contrib import admin

from apps.authz.models import RoleAssignment

from .base import BaseAuthzAdmin


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(BaseAuthzAdmin):
    """Admin for RoleAssignment model."""

    list_display = [
        "id_short",
        "principal",
        "role",
        "content_type",
        "object_id",
        "granted_at",
        "expires_at",
    ]
    list_filter = ["role", "content_type"]
    search_fields = ["principal__username", "role__codename"]
    readonly_fields = [
        "id",
        "granted_at",
        "created_at",
        "updated_at",
        "deleted_at",
    ]

    fieldsets = (
        (None, {"fields": ("principal", "role")}),
        ("Resource", {"fields": ("content_type", "object_id")}),
        ("Grant Info", {"fields": ("granted_by", "granted_at", "expires_at", "reason")}),
        ("Metadata", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="ID", ordering="id")
    def id_short(self, obj: RoleAssignment) -> str:
        return str(obj.pk)[:8] if obj.pk else "—"
