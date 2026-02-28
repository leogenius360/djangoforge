"""
AgentAccount views.
"""

from __future__ import annotations

from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated

from apps.accounts.api.pagination import AccountsPagination
from apps.accounts.api.permissions import IsOwnerOrStaff, IsStaffOrReadOnly
from apps.accounts.api.serializers import AgentAccountCreateSerializer, AgentAccountSerializer
from apps.accounts.models import AgentAccount


class AgentAccountListCreateView(ListCreateAPIView):
    """
    List and create agent accounts.

    GET: Staff see all; non-staff see only owned agents.
    POST: Creates a new AgentAccount with a linked Principal via AccountProvisioner.
    """

    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    pagination_class = AccountsPagination

    def get_queryset(self):
        qs = AgentAccount.objects.select_related("principal", "owner").order_by("-created_at")
        if self.request.user.is_staff:
            return qs
        return qs.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AgentAccountCreateSerializer
        return AgentAccountSerializer


class AgentAccountDetailView(RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or soft-delete an agent account.

    Staff can access any.  Non-staff can only access owned agents.
    """

    permission_classes = [IsAuthenticated, IsOwnerOrStaff]
    serializer_class = AgentAccountSerializer

    def get_queryset(self):
        qs = AgentAccount.objects.select_related("principal", "owner")
        if self.request.user.is_staff:
            return qs
        return qs.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        from apps.accounts.services import AccountProvisioner

        provisioner = AccountProvisioner()
        provisioner.deprovision(instance.principal)
