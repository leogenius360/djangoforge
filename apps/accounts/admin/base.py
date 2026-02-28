"""
Base admin classes for accounts app.

Provides base configurations and mixins for admin interfaces.
"""

from __future__ import annotations

from django.contrib import admin


class BaseAccountsAdmin(admin.ModelAdmin):
    """Base admin class with common configurations for all accounts models."""

    ordering = ["-created_at"]

    def get_readonly_fields(self, request, obj=None):
        """Auto-include created_at and updated_at as readonly fields."""
        readonly = list(super().get_readonly_fields(request, obj))
        for field_name in ("created_at", "updated_at"):
            if hasattr(self.model, field_name) and field_name not in readonly:
                readonly.append(field_name)
        return readonly


class ReadOnlyAdminMixin:
    """Mixin that disables add, change, and delete permissions for read-only admin views."""

    def has_add_permission(self, request):
        """Disable adding records."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing records."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting records."""
        return False
