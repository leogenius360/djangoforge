"""Role admin configuration."""

from __future__ import annotations

from django.contrib import admin

from apps.authz.models import Role, RolePermission

from .base import BaseAuthzAdmin


class RolePermissionInline(admin.TabularInline):
    """Inline for permissions on a role."""

    model = RolePermission
    extra = 1
    autocomplete_fields = ["permission"]


@admin.register(Role)
class RoleAdmin(BaseAuthzAdmin):
    """Admin for Role model."""

    list_display = ["codename", "name", "parent", "content_type", "is_system", "created_at"]
    list_filter = ["is_system", "content_type"]
    search_fields = ["codename", "name"]
    autocomplete_fields = ["parent"]
    inlines = [RolePermissionInline]

    fieldsets = (
        (None, {"fields": ("codename", "name", "description")}),
        ("Scope", {"fields": ("content_type", "parent")}),
        ("Flags", {"fields": ("is_system",)}),
        ("Metadata", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
