"""
APIClient views.
"""

from __future__ import annotations

from apps.accounts.api.pagination import AccountsPagination
from apps.accounts.api.permissions import IsOwnerOrStaff, IsStaffOrReadOnly
from apps.accounts.api.serializers import APIClientCreateSerializer, APIClientSerializer
from apps.accounts.models import APIClient
from apps.core.api.base import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from apps.core.api.permissions import IsAuthenticated


class APIClientListCreateView(ListCreateAPIView):
    """
    List and create API clients.

    GET: Staff see all; non-staff see only owned clients.
    POST: Creates a new APIClient with a linked Principal via AccountProvisioner.
          For confidential clients a secret is generated and returned once.
    """

    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    pagination_class = AccountsPagination

    def get_queryset(self):
        qs = APIClient.objects.select_related("principal", "owner").order_by("-created_at")
        if self.request.user.is_staff:
            return qs
        return qs.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return APIClientCreateSerializer
        return APIClientSerializer


class APIClientDetailView(RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or soft-delete an API client.

    Staff can access any.  Non-staff can only access owned clients.
    """

    permission_classes = [IsAuthenticated, IsOwnerOrStaff]
    serializer_class = APIClientSerializer

    def get_queryset(self):
        qs = APIClient.objects.select_related("principal", "owner")
        if self.request.user.is_staff:
            return qs
        return qs.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        from apps.accounts.services import AccountProvisioner

        provisioner = AccountProvisioner()
        provisioner.deprovision(instance.principal)
