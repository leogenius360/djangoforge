"""Password management serializers."""

from rest_framework import serializers


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for password change (authenticated user)."""

    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for requesting a password reset."""

    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for confirming a password reset."""

    token = serializers.CharField(help_text="Password reset token from email.")
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
