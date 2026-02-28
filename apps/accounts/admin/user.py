"""
UserAccount admin configuration.

NOT extending Django's BaseUserAdmin since UserAccount is no longer AbstractBaseUser.
Principal is the AUTH_USER_MODEL; UserAccount is a profile model linked via OneToOne.
"""

from __future__ import annotations

from django.contrib import admin

from apps.accounts.models import UserAccount

from .base import BaseAccountsAdmin


@admin.register(UserAccount)
class UserAccountAdmin(BaseAccountsAdmin):
    """Admin configuration for the UserAccount model (profile)."""

    list_display = [
        "get_username",
        "get_display_name",
        "given_name",
        "family_name",
        "is_locked_display",
        "is_suspended_display",
        "created_at",
    ]

    fieldsets = (
        ("Account", {"fields": ("principal",)}),
        ("Profile", {"fields": ("given_name", "family_name", "middle_name", "nickname")}),
        ("Details", {"fields": ("picture_url", "gender", "birth_date", "website_url", "bio")}),
        ("Data", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "deleted_at")}),
    )

    readonly_fields = ["principal", "created_at", "updated_at", "deleted_at"]

    search_fields = ["principal__username", "principal__email", "given_name", "family_name"]

    actions = ["soft_delete_users"]

    @admin.display(description="Username", ordering="principal__username")
    def get_username(self, obj):
        """Return the username from the linked Principal."""
        return obj.principal.username

    @admin.display(description="Display Name", ordering="principal__display_name")
    def get_display_name(self, obj):
        """Return the display name from the linked Principal."""
        return obj.principal.display_name

    @admin.display(boolean=True, description="Locked")
    def is_locked_display(self, obj):
        """Display lock status (delegated to Principal)."""
        return obj.is_locked

    @admin.display(boolean=True, description="Suspended")
    def is_suspended_display(self, obj):
        """Display suspension status (delegated to Principal)."""
        return obj.is_suspended

    @admin.action(description="Soft delete selected user accounts")
    def soft_delete_users(self, request, queryset):
        """Soft delete selected user accounts."""
        count = 0
        for user in queryset:
            if not user.is_deleted:
                user.soft_delete()
                count += 1
        self.message_user(request, f"Soft deleted {count} user accounts.")
