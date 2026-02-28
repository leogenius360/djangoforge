"""
AgentAccount serializers.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import AgentAccount
from apps.accounts.services import AccountProvisioner
from apps.accounts.settings import accounts_settings


class AgentAccountSerializer(serializers.ModelSerializer):
    """
    Read/update serializer for AgentAccount.

    Exposes agent-specific fields with read-only lifecycle state
    delegated from the linked Principal.
    """

    # Delegated from Principal (read-only)
    username = serializers.CharField(source="principal.username", read_only=True)
    display_name = serializers.CharField(source="principal.display_name", read_only=True)
    status = serializers.CharField(source="principal.status", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    can_authenticate = serializers.BooleanField(read_only=True)

    class Meta:
        model = AgentAccount
        fields = [
            "id",
            "username",
            "display_name",
            "identifier",
            "agent_type",
            "description",
            "owner",
            "status",
            "is_expired",
            "can_authenticate",
            "allowed_scopes",
            "capabilities",
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


class AgentAccountCreateSerializer(serializers.Serializer):
    """
    Creation serializer for AgentAccount.

    Delegates to ``AccountProvisioner.provision_agent()`` which atomically
    creates both the Principal (kind=AGENT) and the AgentAccount.
    """

    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    identifier = serializers.CharField(max_length=150)
    agent_type = serializers.CharField(max_length=50)
    description = serializers.CharField(required=False, default="")
    owner = serializers.UUIDField(required=False, allow_null=True)
    allowed_scopes = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    capabilities = serializers.DictField(required=False, default=dict)
    metadata = serializers.DictField(required=False, default=dict)

    def validate(self, attrs: dict) -> dict:
        if accounts_settings.AGENT_REQUIRE_OWNER and not attrs.get("owner"):
            request = self.context.get("request")
            if request and request.user.is_authenticated:
                attrs["owner"] = request.user.pk
            else:
                raise serializers.ValidationError({"owner": "An owner is required for agent accounts."})
        return attrs

    def create(self, validated_data: dict) -> AgentAccount:
        from apps.accounts.models import Principal

        owner = None
        owner_id = validated_data.pop("owner", None)
        if owner_id:
            try:
                owner = Principal.objects.get(pk=owner_id)
            except Principal.DoesNotExist as exc:
                raise serializers.ValidationError({"owner": "Principal not found."}) from exc

        provisioner = AccountProvisioner()
        _principal, agent_account = provisioner.provision_agent(
            username=validated_data.get("username") or None,
            identifier=validated_data["identifier"],
            agent_type=validated_data["agent_type"],
            description=validated_data.get("description", ""),
            owner=owner,
            allowed_scopes=validated_data.get("allowed_scopes", []),
            capabilities=validated_data.get("capabilities", {}),
        )
        return agent_account

    def to_representation(self, instance: AgentAccount) -> dict:
        """Use the full serializer for the response."""
        return AgentAccountSerializer(instance, context=self.context).data
