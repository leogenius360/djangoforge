"""Role API views."""

from __future__ import annotations

from apps.authz.api.permissions import IsStaffOrReadOnly, IsStaffUser
from apps.authz.api.serializers.role import (
    RoleCreateSerializer,
    RoleDetailSerializer,
    RolePermissionAddSerializer,
    RolePermissionInlineSerializer,
    RoleSerializer,
    RoleUpdateSerializer,
)
from apps.authz.models import Permission, Role
from apps.authz.services import RoleService
from apps.core.api import status
from apps.core.api.base import (
    ForgeAPIView as APIView,
)
from apps.core.api.base import (
    ListCreateAPIView,
    Response,
    RetrieveUpdateDestroyAPIView,
)
from apps.core.api.decorators import extend_schema
from apps.core.api.permissions import IsAuthenticated


class RoleListCreateView(ListCreateAPIView):
    """
    GET  /api/authz/roles/  — list roles
    POST /api/authz/roles/  — create role (staff only)
    """

    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    filterset_fields = ["content_type", "is_system"]
    search_fields = ["codename", "name"]

    def get_queryset(self):
        return Role.objects.select_related("parent", "content_type").all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return RoleCreateSerializer
        return RoleSerializer


class RoleDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET    /api/authz/roles/<uuid:pk>/
    PATCH  /api/authz/roles/<uuid:pk>/  — staff only
    DELETE /api/authz/roles/<uuid:pk>/  — staff only (soft delete)
    """

    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]

    def get_queryset(self):
        return Role.objects.select_related("parent", "content_type").prefetch_related("role_permissions__permission")

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return RoleUpdateSerializer
        return RoleDetailSerializer

    def perform_destroy(self, instance):
        svc = RoleService()
        svc.delete_role(instance, actor=self.request.user)


class RolePermissionsView(APIView):
    """
    GET    /api/authz/roles/<uuid:pk>/permissions/  — list role permissions
    POST   /api/authz/roles/<uuid:pk>/permissions/  — add permission to role
    DELETE /api/authz/roles/<uuid:pk>/permissions/  — remove permission from role
    """

    permission_classes = [IsAuthenticated, IsStaffUser]

    def _get_role(self, pk):
        return Role.objects.prefetch_related("role_permissions__permission").get(pk=pk)

    @extend_schema(responses=RolePermissionInlineSerializer(many=True))
    def get(self, request, pk):
        role = self._get_role(pk)
        data = RolePermissionInlineSerializer(role.role_permissions.all(), many=True).data
        return Response(data)

    @extend_schema(request=RolePermissionAddSerializer, responses={201: RolePermissionInlineSerializer})
    def post(self, request, pk):
        role = self._get_role(pk)
        serializer = RolePermissionAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        svc = RoleService()
        rp = svc.add_permission(role, serializer.validated_data["permission"])
        return Response(
            RolePermissionInlineSerializer(rp).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=None,
        responses={204: None},
        description="Remove a permission from the role. Pass the permission UUID in the request body.",
    )
    def delete(self, request, pk):
        role = self._get_role(pk)
        perm_id = request.data.get("permission")
        if not perm_id:
            return Response(
                {"permission": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            permission = Permission.objects.get(pk=perm_id)
        except Permission.DoesNotExist:
            return Response(
                {"permission": "Permission not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        svc = RoleService()
        svc.remove_permission(role, permission)
        return Response(status=status.HTTP_204_NO_CONTENT)
