"""Role serializers."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType

from apps.authz.models import Role, RolePermission
from apps.authz.services import RoleService
from apps.core.api import serializers


class RolePermissionInlineSerializer(serializers.ModelSerializer):
    """Inline serializer for permissions attached to a role."""

    permission_codename = serializers.CharField(source="permission.codename", read_only=True)
    permission_name = serializers.CharField(source="permission.name", read_only=True)

    class Meta:
        model = RolePermission
        fields = ["id", "permission", "permission_codename", "permission_name"]
        read_only_fields = ["id"]


class RoleSerializer(serializers.ModelSerializer):
    """Read serializer for Role (list views)."""

    parent_codename = serializers.CharField(source="parent.codename", read_only=True, allow_null=True, default=None)
    permission_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id",
            "codename",
            "name",
            "description",
            "content_type",
            "parent",
            "parent_codename",
            "is_system",
            "permission_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_permission_count(self, obj: Role) -> int:
        return obj.role_permissions.count()


class RoleDetailSerializer(RoleSerializer):
    """Detail serializer for Role (includes permissions and ancestors)."""

    permissions = RolePermissionInlineSerializer(source="role_permissions", many=True, read_only=True)
    ancestors = serializers.SerializerMethodField()

    class Meta(RoleSerializer.Meta):
        fields = RoleSerializer.Meta.fields + ["permissions", "ancestors", "metadata"]

    def get_ancestors(self, obj: Role) -> list[dict]:
        return [{"id": str(r.pk), "codename": r.codename, "name": r.name} for r in obj.get_ancestors()]


class RoleCreateSerializer(serializers.Serializer):
    """Write serializer for Role creation — delegates to RoleService."""

    codename = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="")
    content_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )

    def create(self, validated_data):
        svc = RoleService()
        return svc.create_role(**validated_data)

    def to_representation(self, instance):
        return RoleDetailSerializer(instance, context=self.context).data


class RoleUpdateSerializer(serializers.Serializer):
    """Write serializer for Role updates."""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False)
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(),
        required=False,
        allow_null=True,
    )

    def update(self, instance, validated_data):
        svc = RoleService()
        return svc.update_role(instance, **validated_data)

    def to_representation(self, instance):
        return RoleDetailSerializer(instance, context=self.context).data


class RolePermissionAddSerializer(serializers.Serializer):
    """Serializer for adding permissions to a role."""

    from apps.authz.models import Permission

    permission = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(),
    )
