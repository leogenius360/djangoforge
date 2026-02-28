"""Token management serializers."""

from apps.core.api import serializers


class TokenRefreshSerializer(serializers.Serializer):
    """Request body for refreshing an access token."""

    refresh_token = serializers.CharField(help_text="Opaque refresh token issued at login.")


class TokenRefreshResponseSerializer(serializers.Serializer):
    """Response body from the token refresh endpoint."""

    access_token = serializers.CharField(read_only=True)
    refresh_token = serializers.CharField(read_only=True, help_text="New rotated refresh token.")
    token_type = serializers.CharField(read_only=True)
    expires_in = serializers.IntegerField(read_only=True, help_text="Access token lifetime in seconds.")


class TokenVerifySerializer(serializers.Serializer):
    """Request body for verifying an access token."""

    token = serializers.CharField(help_text="JWT access token to verify.")


class TokenVerifyResponseSerializer(serializers.Serializer):
    """Response body from the token verify endpoint."""

    sub = serializers.CharField(read_only=True, help_text="Principal ID encoded in the token.")
    sid = serializers.CharField(read_only=True, allow_null=True, help_text="Session ID.")
    exp = serializers.IntegerField(read_only=True, help_text="Expiry timestamp (Unix epoch).")
    valid = serializers.BooleanField(read_only=True)
