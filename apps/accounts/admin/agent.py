"""
AgentAccount admin configuration.
"""

from __future__ import annotations

from django.contrib import admin

from apps.accounts.models import AgentAccount

from .base import BaseAccountsAdmin


@admin.register(AgentAccount)
class AgentAccountAdmin(BaseAccountsAdmin):
    """Admin configuration for the AgentAccount model."""

    list_display = ["identifier", "agent_type", "principal", "owner", "is_expired_display", "created_at"]

    fieldsets = (
        ("Agent", {"fields": ("principal", "identifier", "agent_type", "description")}),
        ("Ownership", {"fields": ("owner",)}),
        ("Capabilities", {"fields": ("allowed_scopes", "capabilities")}),
        ("Data", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "deleted_at")}),
    )

    readonly_fields = ["principal", "created_at", "updated_at", "deleted_at"]

    @admin.display(boolean=True, description="Expired")
    def is_expired_display(self, obj):
        """Display expiry status (delegated to Principal)."""
        return obj.is_expired
