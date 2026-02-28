"""
ServiceAccount views.
"""

from __future__ import annotations

from apps.accounts.api.pagination import AccountsPagination
from apps.accounts.api.permissions import IsOwnerOrStaff, IsStaffOrReadOnly
from apps.accounts.api.serializers import ServiceAccountCreateSerializer, ServiceAccountSerializer
from apps.accounts.models import ServiceAccount
from apps.core.api.base import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from apps.core.api.permissions import IsAuthenticated


class ServiceAccountListCreateView(ListCreateAPIView):
    """
    List and create service accounts.

    GET: Staff see all; non-staff see only owned service accounts.
    POST: Creates a new ServiceAccount with a linked Principal via AccountProvisioner.
    """

    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    pagination_class = AccountsPagination

    def get_queryset(self):
        qs = ServiceAccount.objects.select_related("principal", "owner").order_by("-created_at")
        if self.request.user.is_staff:
            return qs
        return qs.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ServiceAccountCreateSerializer
        return ServiceAccountSerializer


class ServiceAccountDetailView(RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or soft-delete a service account.

    Staff can access any.  Non-staff can only access owned accounts.
    """

    permission_classes = [IsAuthenticated, IsOwnerOrStaff]
    serializer_class = ServiceAccountSerializer

    def get_queryset(self):
        qs = ServiceAccount.objects.select_related("principal", "owner")
        if self.request.user.is_staff:
            return qs
        return qs.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        from apps.accounts.services import AccountProvisioner

        provisioner = AccountProvisioner()
        provisioner.deprovision(instance.principal)
