"""Role assignment serializers."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType

from apps.authz.models import Role, RoleAssignment
from apps.authz.services import AssignmentService
from apps.core.api import serializers


class RoleAssignmentSerializer(serializers.ModelSerializer):
    """Read serializer for RoleAssignment."""

    role_codename = serializers.CharField(source="role.codename", read_only=True)
    resource_type_label = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = RoleAssignment
        fields = [
            "id",
            "principal",
            "role",
            "role_codename",
            "content_type",
            "resource_type_label",
            "object_id",
            "granted_by",
            "granted_at",
            "expires_at",
            "is_expired",
            "reason",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "granted_at",
            "is_expired",
            "created_at",
            "updated_at",
        ]

    def get_resource_type_label(self, obj: RoleAssignment) -> str:
        return f"{obj.content_type.app_label}.{obj.content_type.model}"


class RoleAssignmentCreateSerializer(serializers.Serializer):
    """Write serializer for creating role assignments."""

    principal = serializers.UUIDField()
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    resource_type = serializers.CharField(
        max_length=100,
        help_text="Content type as 'app_label.model', e.g. 'accounts.principal'",
    )
    resource_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    reason = serializers.CharField(required=False, default="", max_length=500)

    def validate_principal(self, value):
        from apps.accounts.models import Principal

        try:
            return Principal.objects.get(pk=value)
        except Principal.DoesNotExist:
            raise serializers.ValidationError("Principal not found.") from None

    def validate_resource_type(self, value):
        try:
            app_label, model = value.split(".")
        except ValueError:
            raise serializers.ValidationError("Must be in 'app_label.model' format.") from None
        try:
            return ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(f"Content type {value!r} not found.") from None

    def validate(self, attrs):
        ct = attrs["resource_type"]
        resource_id = attrs["resource_id"]

        model_class = ct.model_class()
        if model_class is None:
            raise serializers.ValidationError({"resource_type": "Cannot resolve model class."})

        try:
            attrs["_resource"] = model_class.objects.get(pk=resource_id)
        except model_class.DoesNotExist:
            raise serializers.ValidationError({"resource_id": "Resource not found."}) from None

        return attrs

    def create(self, validated_data):
        svc = AssignmentService()
        request = self.context.get("request")
        granted_by = request.user if request else None

        return svc.assign_role(
            principal=validated_data["principal"],
            role=validated_data["role"],
            resource=validated_data["_resource"],
            granted_by=granted_by,
            expires_at=validated_data.get("expires_at"),
            reason=validated_data.get("reason", ""),
        )

    def to_representation(self, instance):
        return RoleAssignmentSerializer(instance, context=self.context).data
