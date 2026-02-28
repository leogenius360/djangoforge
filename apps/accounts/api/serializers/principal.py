"""
Principal serializers.

Provides read/write serialization for the Principal model — the root
authentication entity shared by all account kinds (user, service, api_client, agent).

Serializers
-----------
PrincipalSerializer
    Full serializer for staff users.  Exposes all identity, lifecycle, and
    security fields.  Only display/profile fields are writable.

PrincipalPublicSerializer
    Reduced serializer for non-staff users viewing their own principal.
    Omits sensitive staff/security fields (is_staff, is_superuser,
    security_stamp, version, external_id/provider).

PrincipalCreateSerializer
    Creation serializer.  Delegates to ``Principal.objects.create_user()``
    which handles password hashing and the self-bootstrapping actor pattern.
"""

from __future__ import annotations

from apps.accounts.enums import PrincipalKind
from apps.accounts.models import Principal
from apps.accounts.validators import UsernameValidator
from apps.core.api import serializers


class PrincipalSerializer(serializers.ModelSerializer):
    """
    Full Principal serializer for staff users.

    Read-only fields cover identity, authentication state, and security
    metadata.  Writable fields are limited to display/profile information
    that does not affect authentication or security invariants.

    Lifecycle state (is_locked, is_suspended, is_disabled, is_expired,
    can_authenticate) are computed properties exposed as read-only fields.
    """

    # Lifecycle state — computed properties on the model (read-only)
    is_locked = serializers.BooleanField(read_only=True)
    is_suspended = serializers.BooleanField(read_only=True)
    is_disabled = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    can_authenticate = serializers.BooleanField(read_only=True)

    class Meta:
        model = Principal
        fields = [
            "id",
            "kind",
            "username",
            "email",
            "phone_number",
            "display_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "is_locked",
            "is_suspended",
            "is_disabled",
            "is_expired",
            "can_authenticate",
            "last_login",
            "last_seen_at",
            "security_stamp",
            "version",
            "passwordless_enabled",
            "external_id",
            "external_provider",
            "tags",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "kind",
            "username",
            "is_active",
            "is_locked",
            "is_suspended",
            "is_disabled",
            "is_expired",
            "can_authenticate",
            "last_login",
            "last_seen_at",
            "security_stamp",
            "version",
            "created_at",
            "updated_at",
        ]


class PrincipalPublicSerializer(serializers.ModelSerializer):
    """
    Reduced Principal serializer for non-staff users viewing their own principal.

    Omits sensitive staff/security fields (is_staff, is_superuser,
    security_stamp, version, external_id, external_provider).  Writable
    fields are limited to display/profile information.
    """

    # Lifecycle state — computed properties on the model (read-only)
    is_locked = serializers.BooleanField(read_only=True)
    is_suspended = serializers.BooleanField(read_only=True)
    is_disabled = serializers.BooleanField(read_only=True)
    can_authenticate = serializers.BooleanField(read_only=True)

    class Meta:
        model = Principal
        fields = [
            "id",
            "kind",
            "username",
            "email",
            "phone_number",
            "display_name",
            "is_active",
            "is_locked",
            "is_suspended",
            "is_disabled",
            "can_authenticate",
            "last_login",
            "last_seen_at",
            "passwordless_enabled",
            "tags",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "kind",
            "username",
            "is_active",
            "is_locked",
            "is_suspended",
            "is_disabled",
            "can_authenticate",
            "last_login",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]


class PrincipalCreateSerializer(serializers.Serializer):
    """
    Creation serializer for Principal.

    Delegates to ``Principal.objects.create_user()`` which handles password
    hashing and the self-bootstrapping actor pattern (ACTOR_REQUIRED).

    The new principal records itself as its own creator (bootstrap pattern).
    """

    kind = serializers.ChoiceField(choices=PrincipalKind.choices, default=PrincipalKind.USER)
    username = serializers.CharField(max_length=150, validators=[UsernameValidator()])
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_null=True)
    display_name = serializers.CharField(max_length=150, required=False, default="")
    phone_number = serializers.CharField(max_length=17, required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    passwordless_enabled = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value):
        """Reject an email that is already in use."""
        if value and Principal.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A principal with this email already exists.")
        return value

    def validate_username(self, value):
        """Reject a username that is already taken."""
        if Principal.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def create(self, validated_data: dict) -> Principal:
        """Create a new Principal via the manager's create_user contract."""
        from django.db import IntegrityError

        from apps.accounts.exceptions import UsernameConflictError

        try:
            return Principal.objects.create_user(
                username=validated_data["username"],
                password=validated_data.get("password") or None,
                kind=validated_data.get("kind", PrincipalKind.USER),
                email=validated_data.get("email"),
                display_name=validated_data.get("display_name", ""),
                phone_number=validated_data.get("phone_number", ""),
                metadata=validated_data.get("metadata", {}),
                tags=validated_data.get("tags", []),
                passwordless_enabled=validated_data.get("passwordless_enabled", False),
            )
        except UsernameConflictError:
            raise serializers.ValidationError({"username": "This username is already taken."}) from None
        except IntegrityError as exc:
            msg = str(exc).lower()
            if "email" in msg:
                raise serializers.ValidationError({"email": "A principal with this email already exists."}) from exc
            if "username" in msg:
                raise serializers.ValidationError({"username": "This username is already taken."}) from exc
            raise serializers.ValidationError(
                {"non_field_errors": "Could not create principal due to a data conflict."}
            ) from exc

    def to_representation(self, instance: Principal) -> dict:
        """Return the full serializer representation after creation."""
        return PrincipalSerializer(instance, context=self.context).data
