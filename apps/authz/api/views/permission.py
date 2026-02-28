"""Permission API views."""

from __future__ import annotations

from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated

from apps.authz.api.permissions import IsStaffOrReadOnly
from apps.authz.api.serializers.permission import (
    PermissionCreateSerializer,
    PermissionSerializer,
)
from apps.authz.models import Permission


class PermissionListCreateView(ListCreateAPIView):
    """
    GET  /api/authz/permissions/  — list permissions (any authenticated user)
    POST /api/authz/permissions/  — create permission (staff only)
    """

    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    filterset_fields = ["content_type", "action"]
    search_fields = ["codename", "name"]

    def get_queryset(self):
        return Permission.objects.select_related("content_type").all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PermissionCreateSerializer
        return PermissionSerializer


class PermissionDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET    /api/authz/permissions/<uuid:pk>/
    PATCH  /api/authz/permissions/<uuid:pk>/  — staff only
    DELETE /api/authz/permissions/<uuid:pk>/  — staff only
    """

    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    serializer_class = PermissionSerializer

    def get_queryset(self):
        return Permission.objects.select_related("content_type").all()
