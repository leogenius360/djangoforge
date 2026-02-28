"""Policy serializers."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from apps.authz.enums import PolicyEffect
from apps.authz.models import Policy
from apps.authz.services import PolicyService


class PolicySerializer(serializers.ModelSerializer):
    """Read serializer for Policy."""

    content_type_label = serializers.SerializerMethodField()

    class Meta:
        model = Policy
        fields = [
            "id",
            "codename",
            "name",
            "description",
            "effect",
            "condition",
            "priority",
            "content_type",
            "content_type_label",
            "object_id",
            "action",
            "is_enabled",
            "is_system",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_content_type_label(self, obj: Policy) -> str:
        return f"{obj.content_type.app_label}.{obj.content_type.model}"


class PolicyCreateSerializer(serializers.Serializer):
    """Write serializer for Policy creation — delegates to PolicyService."""

    codename = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="")
    effect = serializers.ChoiceField(choices=PolicyEffect.choices)
    condition = serializers.CharField()
    priority = serializers.IntegerField(required=False, default=100)
    content_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
    )
    object_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    action = serializers.CharField(required=False, default="", max_length=20)
    is_enabled = serializers.BooleanField(required=False, default=True)

    def validate_condition(self, value):
        svc = PolicyService()
        try:
            svc.validate_condition(value)
        except Exception:
            raise serializers.ValidationError("Invalid condition expression.") from None
        return value

    def create(self, validated_data):
        svc = PolicyService()
        return svc.create_policy(**validated_data)

    def to_representation(self, instance):
        return PolicySerializer(instance, context=self.context).data


class PolicyUpdateSerializer(serializers.Serializer):
    """Write serializer for Policy updates."""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False)
    condition = serializers.CharField(required=False)
    priority = serializers.IntegerField(required=False)
    action = serializers.CharField(required=False, max_length=20)
    is_enabled = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        svc = PolicyService()
        return svc.update_policy(instance, **validated_data)

    def to_representation(self, instance):
        return PolicySerializer(instance, context=self.context).data
