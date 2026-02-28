"""Policy admin configuration."""

from __future__ import annotations

from django.contrib import admin

from apps.authz.models import Policy

from .base import BaseAuthzAdmin


@admin.register(Policy)
class PolicyAdmin(BaseAuthzAdmin):
    """Admin for Policy model."""

    list_display = [
        "codename",
        "name",
        "effect",
        "priority",
        "content_type",
        "is_enabled",
        "is_system",
        "created_at",
    ]
    list_filter = ["effect", "is_enabled", "is_system", "content_type"]
    search_fields = ["codename", "name"]
    readonly_fields = ["id", "created_at", "updated_at", "deleted_at"]

    fieldsets = (
        (None, {"fields": ("codename", "name", "description")}),
        ("Rule", {"fields": ("effect", "condition", "priority", "action")}),
        ("Scope", {"fields": ("content_type", "object_id")}),
        ("Flags", {"fields": ("is_enabled", "is_system")}),
        ("Metadata", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
