"""
Session admin configuration.

Enterprise-grade session management for multi-device, multi-session authentication.
"""

from datetime import timedelta

from django.contrib import admin

from apps.sessions.models import AuthSession


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    """Admin for auth sessions with enterprise features."""

    list_display = [
        "id",
        "principal_display",
        "device_id",
        "ip_first",
        "created_at",
        "last_seen_at",
        "expires_at",
    ]
    list_filter = [
        "is_trusted_device",
        "created_at",
    ]
    search_fields = [
        "principal__id",
        "ip_first",
        "ip_last",
        "device_id",
        "device_fingerprint",
        "user_agent",
    ]
    readonly_fields = [
        "id",
        "principal",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "deleted_by",
        "last_seen_at",
        "authenticated_at",
        "disabled_at",
        "disabled_by",
        "locked_at",
        "locked_until",
        "suspended_at",
        "suspended_by",
        "revoked_at",
        "logged_out_at",
        "expires_at",
        "idle_expires_at",
    ]
    ordering = ["-last_seen_at"]
    date_hierarchy = "created_at"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "principal",
                )
            },
        ),
        (
            "Session Status & Lifecycle",
            {
                "fields": (
                    "disabled_at",
                    "disabled_by",
                    "disabled_reason",
                    "locked_at",
                    "locked_until",
                    "locked_reason",
                    "suspended_at",
                    "suspended_by",
                    "suspended_reason",
                    "revoked_at",
                    "logged_out_at",
                ),
            },
        ),
        (
            "Authentication",
            {
                "fields": (
                    "auth_status",
                    "auth_method",
                    "mfa_method",
                    "authenticated_at",
                ),
            },
        ),
        (
            "Authorization (Scopes)",
            {
                "fields": ("scopes",),
            },
        ),
        (
            "Device Info",
            {
                "fields": (
                    "device_id",
                    "device_fingerprint",
                    "channel",
                    "user_agent",
                    "is_trusted_device",
                ),
            },
        ),
        (
            "Network Info",
            {
                "fields": (
                    "ip_first",
                    "ip_last",
                ),
            },
        ),
        (
            "Token Management",
            {
                "fields": ("security_stamp_at_issue",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "last_seen_at",
                    "expires_at",
                    "idle_expires_at",
                ),
            },
        ),
        (
            "Metadata & Audit",
            {
                "fields": ("metadata", "created_by", "updated_by", "deleted_by"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = [
        "revoke_sessions",
        "lock_sessions",
        "unlock_sessions",
        "suspend_sessions",
        "unsuspend_sessions",
    ]

    @admin.display(description="Principal")
    def principal_display(self, obj):
        """Display principal."""
        if obj.principal:
            return f"{obj.principal.kind}: {obj.principal.id}"
        return "No Principal"

    @admin.action(description="Revoke selected sessions")
    def revoke_sessions(self, request, queryset):
        """Revoke/terminate selected sessions."""
        count = 0
        for session in queryset:
            if not session.is_deleted and not session.is_disabled:
                session.revoke(reason="Admin action")
                count += 1
        self.message_user(request, f"Revoked {count} sessions.")

    @admin.action(description="Lock selected sessions (30 min)")
    def lock_sessions(self, request, queryset):
        """Lock selected sessions."""
        # Get admin user's principal (request.user IS the Principal)
        admin_principal = request.user if request.user.is_authenticated else None

        count = 0
        for session in queryset:
            if session.is_active and not session.is_locked:
                session.lock(actor=admin_principal, reason="Admin action", duration=timedelta(minutes=30))
                count += 1
        self.message_user(request, f"Locked {count} sessions.")

    @admin.action(description="Unlock selected sessions")
    def unlock_sessions(self, request, queryset):
        """Unlock selected sessions."""
        count = 0
        for session in queryset:
            if session.is_locked:
                session.unlock()
                count += 1
        self.message_user(request, f"Unlocked {count} sessions.")

    @admin.action(description="Suspend selected sessions")
    def suspend_sessions(self, request, queryset):
        """Suspend selected sessions."""
        # Get admin user's principal (request.user IS the Principal)
        admin_principal = request.user if request.user.is_authenticated else None

        count = 0
        for session in queryset:
            if session.is_active and not session.is_suspended:
                session.suspend(reason="Admin action", suspended_by=admin_principal)
                count += 1
        self.message_user(request, f"Suspended {count} sessions.")

    @admin.action(description="Unsuspend selected sessions")
    def unsuspend_sessions(self, request, queryset):
        """Unsuspend selected sessions."""
        count = 0
        for session in queryset:
            if session.is_suspended:
                session.unsuspend()
                count += 1
        self.message_user(request, f"Unsuspended {count} sessions.")
