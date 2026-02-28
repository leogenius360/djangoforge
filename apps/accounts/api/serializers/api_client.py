"""
APIClient serializers.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import APIClient
from apps.accounts.services import AccountProvisioner


class APIClientSerializer(serializers.ModelSerializer):
    """
    Read/update serializer for APIClient.

    The ``client_secret`` field is never exposed in read operations.
    """

    # Delegated from Principal (read-only)
    username = serializers.CharField(source="principal.username", read_only=True)
    display_name = serializers.CharField(source="principal.display_name", read_only=True)
    status = serializers.CharField(source="principal.status", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    can_authenticate = serializers.BooleanField(read_only=True)

    class Meta:
        model = APIClient
        fields = [
            "id",
            "username",
            "display_name",
            "client_id",
            "client_type",
            "redirect_uris",
            "allowed_scopes",
            "grant_types",
            "owner",
            "status",
            "is_expired",
            "can_authenticate",
            "website_url",
            "terms_url",
            "privacy_url",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "username",
            "display_name",
            "client_id",
            "status",
            "is_expired",
            "can_authenticate",
            "created_at",
            "updated_at",
        ]


class APIClientCreateSerializer(serializers.Serializer):
    """
    Creation serializer for APIClient.

    Delegates to ``AccountProvisioner.provision_api_client()`` which atomically
    creates the Principal (kind=API_CLIENT) and the APIClient.
    For confidential clients a secret is generated and returned exactly once.
    """

    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    client_id = serializers.CharField(max_length=255)
    client_type = serializers.ChoiceField(
        choices=APIClient.ClientType.choices,
        default=APIClient.ClientType.CONFIDENTIAL,
    )
    redirect_uris = serializers.ListField(child=serializers.URLField(), required=False, default=list)
    allowed_scopes = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    grant_types = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    owner = serializers.UUIDField(required=False, allow_null=True)
    website_url = serializers.URLField(required=False, default="", allow_blank=True)
    terms_url = serializers.URLField(required=False, default="", allow_blank=True)
    privacy_url = serializers.URLField(required=False, default="", allow_blank=True)
    metadata = serializers.DictField(required=False, default=dict)

    def create(self, validated_data: dict) -> APIClient:
        from apps.accounts.models import Principal

        request = self.context.get("request")

        owner = None
        owner_id = validated_data.pop("owner", None)
        if owner_id:
            owner = Principal.objects.get(pk=owner_id)
        elif request and request.user.is_authenticated:
            owner = request.user

        provisioner = AccountProvisioner()
        _principal, api_client, plaintext_secret = provisioner.provision_api_client(
            username=validated_data.get("username") or None,
            client_id=validated_data["client_id"],
            client_type=validated_data.get("client_type", "confidential"),
            owner=owner,
            redirect_uris=validated_data.get("redirect_uris", []),
            allowed_scopes=validated_data.get("allowed_scopes", []),
            grant_types=validated_data.get("grant_types", []),
            website_url=validated_data.get("website_url", ""),
            terms_url=validated_data.get("terms_url", ""),
            privacy_url=validated_data.get("privacy_url", ""),
        )

        # Attach plaintext secret for one-time display
        api_client._plaintext_secret = plaintext_secret
        return api_client

    def to_representation(self, instance: APIClient) -> dict:
        """Include one-time plaintext secret in creation response."""
        data = APIClientSerializer(instance, context=self.context).data
        plaintext = getattr(instance, "_plaintext_secret", None)
        if plaintext:
            data["client_secret"] = plaintext
        return data
