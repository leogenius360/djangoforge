"""
APIClient admin configuration.
"""

from __future__ import annotations

from django.contrib import admin

from apps.accounts.models import APIClient

from .base import BaseAccountsAdmin


@admin.register(APIClient)
class APIClientAdmin(BaseAccountsAdmin):
    """Admin configuration for the APIClient model."""

    list_display = ["client_id", "principal", "client_type", "owner", "created_at"]

    fieldsets = (
        ("Client", {"fields": ("principal", "client_id", "client_type")}),
        ("OAuth", {"fields": ("redirect_uris", "allowed_scopes", "grant_types")}),
        ("Ownership", {"fields": ("owner",)}),
        ("URLs", {"fields": ("website_url", "terms_url", "privacy_url")}),
        ("Data", {"fields": ("metadata",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "deleted_at")}),
    )

    readonly_fields = ["principal", "created_at", "updated_at", "deleted_at"]
