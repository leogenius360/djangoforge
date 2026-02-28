"""Verification serializers."""

from rest_framework import serializers


class EmailVerificationRequestSerializer(serializers.Serializer):
    """Serializer for requesting email verification (no input needed)."""


class EmailVerificationConfirmSerializer(serializers.Serializer):
    """Serializer for confirming email verification."""

    token = serializers.CharField(help_text="Verification token from email.")


class PhoneVerificationRequestSerializer(serializers.Serializer):
    """Serializer for requesting phone verification (no input needed)."""


class PhoneVerificationConfirmSerializer(serializers.Serializer):
    """Serializer for confirming phone verification."""

    otp = serializers.CharField(max_length=10, help_text="OTP code from SMS.")
