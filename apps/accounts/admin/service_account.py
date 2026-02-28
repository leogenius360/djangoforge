"""
ServiceAccount admin configuration.
"""

from __future__ import annotations

from django.contrib import admin

from apps.accounts.models import ServiceAccount

from .base import BaseAccountsAdmin


@admin.register(ServiceAccount)
class ServiceAccountAdmin(BaseAccountsAdmin):
    """Admin configuration for the ServiceAccount model."""

    list_display = ["service_name", "name", "principal", "is_expired_display", "owner", "created_at"]

    fieldsets = (
        ("Info", {"fields": ("principal", "name", "service_name", "description")}),
        ("Ownership", {"fields": ("owner",)}),
        ("Scopes", {"fields": ("allowed_scopes",)}),
        ("Data", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "deleted_at")}),
    )

    readonly_fields = ["principal", "created_at", "updated_at", "deleted_at"]

    @admin.display(boolean=True, description="Expired")
    def is_expired_display(self, obj):
        """Display expiry status (delegated to Principal)."""
        return obj.is_expired
