"""Policy API views."""

from __future__ import annotations

from apps.authz.api.permissions import IsStaffUser
from apps.authz.api.serializers.policy import (
    PolicyCreateSerializer,
    PolicySerializer,
    PolicyUpdateSerializer,
)
from apps.authz.models import Policy
from apps.authz.services import PolicyService
from apps.core.api.base import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from apps.core.api.permissions import IsAuthenticated


class PolicyListCreateView(ListCreateAPIView):
    """
    GET  /api/authz/policies/  — list policies (staff only)
    POST /api/authz/policies/  — create policy (staff only)
    """

    permission_classes = [IsAuthenticated, IsStaffUser]
    filterset_fields = ["effect", "content_type", "is_enabled"]
    search_fields = ["codename", "name"]

    def get_queryset(self):
        return Policy.objects.select_related("content_type").all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PolicyCreateSerializer
        return PolicySerializer


class PolicyDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET    /api/authz/policies/<uuid:pk>/
    PATCH  /api/authz/policies/<uuid:pk>/
    DELETE /api/authz/policies/<uuid:pk>/  — soft delete
    """

    permission_classes = [IsAuthenticated, IsStaffUser]

    def get_queryset(self):
        return Policy.objects.select_related("content_type").all()

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return PolicyUpdateSerializer
        return PolicySerializer

    def perform_destroy(self, instance):
        svc = PolicyService()
        svc.delete_policy(instance, actor=self.request.user)
