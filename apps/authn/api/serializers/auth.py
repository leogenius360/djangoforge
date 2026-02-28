"""Authentication serializers."""

from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    """Serializer for password-based login."""

    identifier = serializers.CharField(help_text="Email, username, or phone number.")
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class MFALoginSerializer(serializers.Serializer):
    """Serializer for MFA verification during login."""

    mfa_token = serializers.CharField(max_length=128, help_text="MFA temporary token from login response.")
    code = serializers.CharField(max_length=12, help_text="TOTP code or backup code.")


class PasswordlessRequestSerializer(serializers.Serializer):
    """Serializer for requesting passwordless login."""

    METHOD_CHOICES = [
        ("email", "Magic link (email)"),
        ("email_otp", "Email OTP"),
        ("sms", "SMS OTP"),
    ]

    method = serializers.ChoiceField(choices=METHOD_CHOICES, required=False, default="email")
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(required=False)

    def validate(self, attrs):
        method = attrs.get("method", "email")
        email = attrs.get("email")
        phone_number = attrs.get("phone_number")

        if method in ("email", "email_otp") and not email:
            raise serializers.ValidationError({"email": "Email is required for this method."})

        if method == "sms" and not phone_number:
            raise serializers.ValidationError({"phone_number": "Phone number is required for SMS method."})

        if email:
            attrs["email"] = email.lower()

        return attrs


class PasswordlessVerifySerializer(serializers.Serializer):
    """Serializer for verifying passwordless login."""

    token = serializers.CharField(help_text="Magic link token.")
    otp = serializers.CharField(max_length=10, required=False, help_text="OTP code (for OTP-based flows).")


class PasswordlessTOTPLoginSerializer(serializers.Serializer):
    """Serializer for TOTP-only login (no password)."""

    identifier = serializers.CharField(help_text="Email, username, or phone number.")
    code = serializers.CharField(max_length=8, help_text="TOTP code.")


class LogoutSerializer(serializers.Serializer):
    """Request body for logout."""

    all_sessions = serializers.BooleanField(
        default=False,
        required=False,
        help_text="Set to true to terminate all active sessions for this principal.",
    )


class AuthResponseSerializer(serializers.Serializer):
    """JWT authentication response returned by login endpoints."""

    access_token = serializers.CharField(read_only=True)
    refresh_token = serializers.CharField(read_only=True)
    token_type = serializers.CharField(read_only=True)
    expires_in = serializers.IntegerField(read_only=True)
    principal_id = serializers.CharField(read_only=True)
    session_id = serializers.CharField(read_only=True)
    auth_method = serializers.CharField(read_only=True)
