"""
Principal admin configuration.
"""

from __future__ import annotations

from django.contrib import admin

from apps.accounts.models import Principal

from .base import BaseAccountsAdmin


@admin.register(Principal)
class PrincipalAdmin(BaseAccountsAdmin):
    """Admin configuration for the Principal model (AUTH_USER_MODEL)."""

    list_display = ["username", "kind", "display_name", "email", "is_staff", "created_at"]

    fieldsets = (
        ("Identity", {"fields": ("username", "kind", "display_name", "email")}),
        ("Status", {"fields": ("is_staff", "is_superuser")}),
        ("Security", {"fields": ("security_stamp", "version")}),
        (
            "Lifecycle",
            {
                "fields": (
                    "disabled_at",
                    "disabled_by",
                    "disabled_reason",
                    "locked_at",
                    "locked_until",
                    "locked_by",
                    "locked_reason",
                    "suspended_at",
                    "suspended_by",
                    "suspended_reason",
                    "expires_at",
                ),
            },
        ),
        ("Metadata", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "deleted_at")}),
    )

    readonly_fields = ["id", "created_at", "updated_at", "deleted_at", "security_stamp", "version"]

    list_filter = ["kind", "is_staff"]
    search_fields = ["username", "display_name", "email", "id"]
