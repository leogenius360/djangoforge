"""Role assignment API views."""

from __future__ import annotations

from rest_framework.generics import ListCreateAPIView, RetrieveDestroyAPIView
from rest_framework.permissions import IsAuthenticated

from apps.authz.api.serializers.assignment import (
    RoleAssignmentCreateSerializer,
    RoleAssignmentSerializer,
)
from apps.authz.models import RoleAssignment


class RoleAssignmentListCreateView(ListCreateAPIView):
    """
    GET  /api/authz/assignments/  — list assignments
    POST /api/authz/assignments/  — create assignment
    """

    permission_classes = [IsAuthenticated]
    filterset_fields = ["principal", "role", "content_type"]

    def get_queryset(self):
        return RoleAssignment.objects.active().select_related("role", "content_type", "principal", "granted_by").all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return RoleAssignmentCreateSerializer
        return RoleAssignmentSerializer


class RoleAssignmentDetailView(RetrieveDestroyAPIView):
    """
    GET    /api/authz/assignments/<uuid:pk>/
    DELETE /api/authz/assignments/<uuid:pk>/  — revoke (soft delete)
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RoleAssignmentSerializer

    def get_queryset(self):
        return RoleAssignment.objects.active().select_related("role", "content_type", "principal", "granted_by").all()

    def perform_destroy(self, instance):
        instance.soft_delete(actor=self.request.user)
