"""
UserAccount serializers.

Provides read/write serialization for user account profile fields with
read-only principal identity/lifecycle fields delegated from the linked Principal.
"""

from __future__ import annotations

from apps.accounts.exceptions import ProvisioningError, UsernameConflictError
from apps.accounts.models import UserAccount
from apps.accounts.models.principal import Principal
from apps.accounts.services import AccountProvisioner
from apps.accounts.validators import UsernameValidator
from apps.core.api import serializers


class UserAccountSerializer(serializers.ModelSerializer):
    """
    Full UserAccount serializer for authenticated users.

    Read-only fields are delegated from Principal (identity, lifecycle state)
    or computed properties (verification status).  Write operations only
    affect UserAccount-specific profile fields.
    """

    # Delegated from Principal (read-only)
    username = serializers.CharField(source="principal.username", read_only=True)
    email = serializers.EmailField(source="principal.email", read_only=True)
    phone_number = serializers.CharField(source="principal.phone_number", read_only=True)
    display_name = serializers.CharField(source="principal.display_name", read_only=True)
    status = serializers.CharField(source="principal.status", read_only=True)
    is_active = serializers.BooleanField(source="principal.is_active", read_only=True)
    is_locked = serializers.BooleanField(read_only=True)
    is_suspended = serializers.BooleanField(read_only=True)
    is_disabled = serializers.BooleanField(read_only=True)
    can_authenticate = serializers.BooleanField(read_only=True)

    # Computed properties (read-only)
    is_email_verified = serializers.BooleanField(read_only=True)
    is_phone_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserAccount
        fields = [
            "id",
            "username",
            "email",
            "phone_number",
            "display_name",
            "status",
            "is_active",
            "is_locked",
            "is_suspended",
            "is_disabled",
            "can_authenticate",
            "is_email_verified",
            "is_phone_verified",
            # Profile fields
            "given_name",
            "family_name",
            "middle_name",
            "nickname",
            "picture_url",
            "gender",
            "birth_date",
            "website_url",
            "bio",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "username",
            "email",
            "phone_number",
            "display_name",
            "status",
            "is_active",
            "is_locked",
            "is_suspended",
            "is_disabled",
            "can_authenticate",
            "is_email_verified",
            "is_phone_verified",
            "created_at",
            "updated_at",
        ]


class UserAccountCreateSerializer(serializers.Serializer):
    """
    Creation serializer for UserAccount.

    Delegates to ``AccountProvisioner.provision_user()`` which atomically
    creates both the Principal (kind=USER) and the UserAccount.
    """

    username = serializers.CharField(max_length=150, validators=[UsernameValidator()])
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_null=True)
    display_name = serializers.CharField(max_length=150, required=False, default="")
    phone_number = serializers.CharField(max_length=17, required=False, allow_null=True)

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

    def create(self, validated_data: dict) -> UserAccount:
        provisioner = AccountProvisioner()
        try:
            _principal, user_account = provisioner.provision_user(
                username=validated_data["username"],
                password=validated_data.get("password") or None,
                email=validated_data.get("email"),
                display_name=validated_data.get("display_name", ""),
                phone_number=validated_data.get("phone_number"),
            )
        except UsernameConflictError:
            raise serializers.ValidationError({"username": "This username is already taken."}) from None
        except ProvisioningError as exc:
            msg = str(exc)
            if "email" in msg.lower():
                raise serializers.ValidationError({"email": "A principal with this email already exists."}) from exc
            raise serializers.ValidationError({"non_field_errors": msg}) from exc
        return user_account

    def to_representation(self, instance: UserAccount) -> dict:
        """Use the full serializer for the response."""
        return UserAccountSerializer(instance, context=self.context).data


class UserAccountPublicSerializer(serializers.ModelSerializer):
    """Minimal public serializer exposing only non-sensitive identity fields."""

    username = serializers.CharField(source="principal.username", read_only=True)
    display_name = serializers.CharField(source="principal.display_name", read_only=True)

    class Meta:
        model = UserAccount
        fields = [
            "id",
            "username",
            "display_name",
        ]
        read_only_fields = fields
