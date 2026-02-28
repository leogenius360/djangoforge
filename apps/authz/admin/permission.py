"""Permission admin configuration."""

from __future__ import annotations

from django.contrib import admin

from apps.authz.models import Permission

from .base import BaseAuthzAdmin


@admin.register(Permission)
class PermissionAdmin(BaseAuthzAdmin):
    """Admin for Permission model."""

    list_display = ["codename", "name", "content_type", "action", "created_at"]
    list_filter = ["action", "content_type"]
    search_fields = ["codename", "name"]
    readonly_fields = ["id", "codename", "created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("codename", "name", "description")}),
        ("Scope", {"fields": ("content_type", "action")}),
        ("Metadata", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
