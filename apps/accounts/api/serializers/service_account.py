"""
ServiceAccount serializers.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import ServiceAccount
from apps.accounts.services import AccountProvisioner
from apps.accounts.settings import accounts_settings


class ServiceAccountSerializer(serializers.ModelSerializer):
    """
    Read/update serializer for ServiceAccount.

    Exposes service-specific fields with read-only lifecycle state
    delegated from the linked Principal.
    """

    # Delegated from Principal (read-only)
    username = serializers.CharField(source="principal.username", read_only=True)
    display_name = serializers.CharField(source="principal.display_name", read_only=True)
    status = serializers.CharField(source="principal.status", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    can_authenticate = serializers.BooleanField(read_only=True)

    class Meta:
        model = ServiceAccount
        fields = [
            "id",
            "username",
            "display_name",
            "name",
            "service_name",
            "description",
            "owner",
            "status",
            "is_expired",
            "can_authenticate",
            "allowed_scopes",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "username",
            "display_name",
            "status",
            "is_expired",
            "can_authenticate",
            "created_at",
            "updated_at",
        ]

    def validate_allowed_scopes(self, value: list) -> list:
        max_scopes = accounts_settings.SERVICE_ACCOUNT_MAX_SCOPES
        if len(value) > max_scopes:
            raise serializers.ValidationError(f"Maximum {max_scopes} scopes allowed.")
        return value


class ServiceAccountCreateSerializer(serializers.Serializer):
    """
    Creation serializer for ServiceAccount.

    Delegates to ``AccountProvisioner.provision_service_account()`` which
    atomically creates both the Principal (kind=SERVICE) and the ServiceAccount.
    """

    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    service_name = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=150, required=False, default="")
    description = serializers.CharField(required=False, default="")
    owner = serializers.UUIDField(required=False, allow_null=True)
    allowed_scopes = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    metadata = serializers.DictField(required=False, default=dict)

    def validate_allowed_scopes(self, value: list) -> list:
        max_scopes = accounts_settings.SERVICE_ACCOUNT_MAX_SCOPES
        if len(value) > max_scopes:
            raise serializers.ValidationError(f"Maximum {max_scopes} scopes allowed.")
        return value

    def create(self, validated_data: dict) -> ServiceAccount:
        from apps.accounts.models import Principal

        request = self.context.get("request")

        owner = None
        owner_id = validated_data.pop("owner", None)
        if owner_id:
            owner = Principal.objects.get(pk=owner_id)
        elif request and request.user.is_authenticated:
            owner = request.user

        provisioner = AccountProvisioner()
        _principal, service_account = provisioner.provision_service_account(
            username=validated_data.get("username") or None,
            service_name=validated_data["service_name"],
            name=validated_data.get("name", ""),
            description=validated_data.get("description", ""),
            owner=owner,
            allowed_scopes=validated_data.get("allowed_scopes", []),
        )
        return service_account

    def to_representation(self, instance: ServiceAccount) -> dict:
        """Use the full serializer for the response."""
        return ServiceAccountSerializer(instance, context=self.context).data
