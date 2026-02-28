"""MFA serializers."""

from rest_framework import serializers


class MFASetupResponseSerializer(serializers.Serializer):
    """Response serializer for MFA setup (read-only)."""

    secret = serializers.CharField(read_only=True)
    provisioning_uri = serializers.CharField(read_only=True)
    credential_id = serializers.CharField(read_only=True)


class MFAVerifySetupSerializer(serializers.Serializer):
    """Serializer for verifying MFA setup."""

    code = serializers.CharField(max_length=6, min_length=6)

    def validate_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Code must be 6 digits.")
        return value


class MFADisableSerializer(serializers.Serializer):
    """Serializer for disabling MFA."""

    code = serializers.CharField(max_length=12, help_text="TOTP code or backup code.")


class MFAStatusSerializer(serializers.Serializer):
    """Response serializer for MFA status (read-only)."""

    enabled = serializers.BooleanField(read_only=True)
    totp_count = serializers.IntegerField(read_only=True)
    backup_codes_remaining = serializers.IntegerField(read_only=True)
    last_used = serializers.DateTimeField(read_only=True, allow_null=True)


class BackupCodesRegenerateSerializer(serializers.Serializer):
    """Response serializer for regenerating backup codes."""

    backup_codes = serializers.ListField(child=serializers.CharField(), read_only=True)
    detail = serializers.CharField(read_only=True)


class MFAActivateResponseSerializer(serializers.Serializer):
    """Response for activating MFA (POST /mfa/setup/)."""

    detail = serializers.CharField(read_only=True)
    backup_codes = serializers.ListField(child=serializers.CharField(), read_only=True)


class MFADisableResponseSerializer(serializers.Serializer):
    """Response for disabling MFA (POST /mfa/disable/)."""

    detail = serializers.CharField(read_only=True)
    credentials_revoked = serializers.IntegerField(read_only=True)
