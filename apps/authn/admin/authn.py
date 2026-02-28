"""
Credential and model admin configuration for authn app.
"""

from django.contrib import admin

from apps.authn.models import (
    BackupCode,
    LoginAttempt,
    MFAPendingAuthentication,
    PasswordCredential,
    PasswordHistory,
    TOTPCredential,
    VerificationToken,
    WebAuthnCredential,
)


@admin.register(PasswordCredential)
class PasswordCredentialAdmin(admin.ModelAdmin):
    list_display = [
        "principal",
        "status",
        "strength_score",
        "is_compromised",
        "require_change",
        "last_used_at",
        "created_at",
    ]
    list_filter = ["status", "is_compromised", "require_change", "created_at"]
    search_fields = ["principal__email"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "deleted_at", "last_used_at", "version"]


@admin.register(WebAuthnCredential)
class WebAuthnCredentialAdmin(admin.ModelAdmin):
    list_display = [
        "principal",
        "label",
        "status",
        "sign_count",
        "backup_eligible",
        "last_used_at",
        "created_at",
    ]
    list_filter = ["status", "backup_eligible", "created_at"]
    search_fields = ["principal__email", "label", "aaguid"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "deleted_at", "last_used_at", "version", "sign_count"]


@admin.register(TOTPCredential)
class TOTPCredentialAdmin(admin.ModelAdmin):
    list_display = [
        "principal",
        "label",
        "status",
        "algorithm",
        "digits",
        "period",
        "last_used_at",
        "created_at",
    ]
    list_filter = ["status", "algorithm", "created_at"]
    search_fields = ["principal__email", "label"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "deleted_at", "last_used_at", "version"]


@admin.register(BackupCode)
class BackupCodeAdmin(admin.ModelAdmin):
    list_display = ["principal", "status", "is_used", "used_at", "created_at"]
    list_filter = ["status", "is_used", "created_at"]
    search_fields = ["principal__email"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "deleted_at", "used_at", "is_used", "version"]


@admin.register(VerificationToken)
class VerificationTokenAdmin(admin.ModelAdmin):
    list_display = [
        "principal",
        "purpose",
        "is_valid_display",
        "attempt_count",
        "max_attempts",
        "created_at",
        "expires_at",
        "used_at",
    ]
    list_filter = ["purpose", "created_at"]
    search_fields = ["principal__email", "delivery_target"]
    ordering = ["-created_at"]
    readonly_fields = [
        "id",
        "token_hash",
        "otp_hash",
        "attempt_count",
        "created_at",
        "updated_at",
        "used_at",
        "version",
    ]

    @admin.display(boolean=True, description="Valid")
    def is_valid_display(self, obj):
        return obj.is_valid


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = [
        "identifier",
        "result",
        "auth_method",
        "ip_address",
        "created_at",
    ]
    list_filter = ["result", "auth_method", "created_at"]
    search_fields = ["identifier", "ip_address", "principal__email"]
    ordering = ["-created_at"]
    readonly_fields = [
        "id",
        "principal",
        "identifier",
        "result",
        "auth_method",
        "ip_address",
        "user_agent",
        "failure_reason",
        "metadata",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PasswordHistory)
class PasswordHistoryAdmin(admin.ModelAdmin):
    list_display = ["principal", "set_by", "created_at"]
    list_filter = ["set_by", "created_at"]
    search_fields = ["principal__email"]
    ordering = ["-created_at"]
    readonly_fields = ["id", "principal", "password_hash", "set_by", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MFAPendingAuthentication)
class MFAPendingAuthenticationAdmin(admin.ModelAdmin):
    list_display = [
        "principal",
        "auth_method",
        "is_valid_display",
        "attempt_count",
        "max_attempts",
        "created_at",
        "expires_at",
        "consumed_at",
    ]
    list_filter = ["auth_method", "created_at"]
    search_fields = ["principal__email"]
    ordering = ["-created_at"]
    readonly_fields = [
        "id",
        "token_hash",
        "attempt_count",
        "consumed_at",
        "created_at",
        "updated_at",
        "version",
    ]

    @admin.display(boolean=True, description="Valid")
    def is_valid_display(self, obj):
        return obj.is_valid
