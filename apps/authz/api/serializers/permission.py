"""Permission serializers."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from apps.authz.enums import PermissionAction
from apps.authz.models import Permission


class PermissionSerializer(serializers.ModelSerializer):
    """Read serializer for Permission."""

    content_type_label = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = [
            "id",
            "codename",
            "name",
            "description",
            "content_type",
            "content_type_label",
            "action",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "codename", "created_at", "updated_at"]

    def get_content_type_label(self, obj: Permission) -> str:
        return f"{obj.content_type.app_label}.{obj.content_type.model}"


class PermissionCreateSerializer(serializers.Serializer):
    """Write serializer for Permission creation."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="")
    content_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
    )
    action = serializers.ChoiceField(choices=PermissionAction.choices)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        ct = attrs["content_type"]
        action = attrs["action"]

        codename = Permission.build_codename(ct, action)
        if Permission.objects.filter(codename=codename).exists():
            raise serializers.ValidationError(f"Permission {codename!r} already exists.")
        attrs["codename"] = codename
        return attrs

    def create(self, validated_data):
        return Permission.objects.create(**validated_data)

    def to_representation(self, instance):
        return PermissionSerializer(instance, context=self.context).data
