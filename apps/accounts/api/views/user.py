"""
UserAccount views.
"""

from __future__ import annotations

from apps.accounts.api.pagination import AccountsPagination
from apps.accounts.api.permissions import IsOwnerOrStaff, IsStaffOrReadOnly
from apps.accounts.api.serializers import (
    UserAccountCreateSerializer,
    UserAccountPublicSerializer,
    UserAccountSerializer,
)
from apps.accounts.models import UserAccount
from apps.core.api.base import ListCreateAPIView, RetrieveUpdateAPIView
from apps.core.api.permissions import AllowAny, IsAuthenticated


class UserAccountListView(ListCreateAPIView):
    """
    List and create user accounts.

    GET: Staff see all accounts.  Non-staff users see only their own.
    POST: Public — allows unauthenticated signup via AccountProvisioner.
    """

    pagination_class = AccountsPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAuthenticated(), IsStaffOrReadOnly()]

    def get_queryset(self):
        qs = UserAccount.objects.select_related("principal").order_by("-created_at")
        if self.request.user.is_staff:
            return qs
        return qs.filter(principal=self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserAccountCreateSerializer
        if self.request.user.is_staff:
            return UserAccountSerializer
        return UserAccountPublicSerializer


class UserAccountDetailView(RetrieveUpdateAPIView):
    """
    Retrieve or update a single user account.

    Staff can access any account.  Non-staff can only access their own.
    """

    permission_classes = [IsAuthenticated, IsOwnerOrStaff]
    serializer_class = UserAccountSerializer

    def get_queryset(self):
        qs = UserAccount.objects.select_related("principal")
        if self.request.user.is_staff:
            return qs
        return qs.filter(principal=self.request.user)
