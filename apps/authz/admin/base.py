"""Base admin classes for the authz app."""

from __future__ import annotations

from django.contrib import admin


class BaseAuthzAdmin(admin.ModelAdmin):
    """Shared admin configuration for authz models."""

    ordering = ["-created_at"]

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for field_name in ("created_at", "updated_at", "deleted_at"):
            if hasattr(self.model, field_name) and field_name not in readonly:
                readonly.append(field_name)
        return readonly
