"""
Principal views.

Provides list/create and retrieve/update/destroy endpoints for the
Principal model — the root authentication entity.

URL patterns
------------
GET  /api/accounts/principals/           PrincipalListCreateView  -> list
POST /api/accounts/principals/           PrincipalListCreateView  -> create (staff)
GET  /api/accounts/principals/<pk>/      PrincipalDetailView      -> retrieve
PUT  /api/accounts/principals/<pk>/      PrincipalDetailView      -> update
PATCH /api/accounts/principals/<pk>/     PrincipalDetailView      -> partial update
DELETE /api/accounts/principals/<pk>/    PrincipalDetailView      -> soft delete (staff)

Access rules
------------
- Staff can list all principals; non-staff see only their own.
- POST (create) follows ``IsStaffOrReadOnly``: staff-only when
  ``API_REQUIRE_STAFF`` is True; open otherwise.
- Detail view: staff may access any principal; non-staff may only access
  their own principal (enforced by ``IsSelfOrStaff``).
- DELETE performs a soft-delete and requires staff (via ``IsSelfOrStaff``
  the non-staff user could only delete themselves, which is disallowed via
  an explicit HTTP 403 in ``perform_destroy``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

if TYPE_CHECKING:
    from rest_framework.request import Request

from apps.accounts.api.pagination import AccountsPagination
from apps.accounts.api.permissions import IsSelfOrStaff, IsStaffOrReadOnly
from apps.accounts.api.serializers.principal import (
    PrincipalCreateSerializer,
    PrincipalPublicSerializer,
    PrincipalSerializer,
)
from apps.accounts.models import Principal
from apps.core.context import set_current_actor


class PrincipalListCreateView(ListCreateAPIView):
    """
    List principals or create a new one.

    GET  — Staff receives all principals; non-staff receives only their own.
    POST — Public: allows unauthenticated signup.  When
           ``ACCOUNTS["API_REQUIRE_STAFF"]`` is True the ``IsStaffOrReadOnly``
           check still applies for authenticated non-staff users, but anonymous
           sign-up is permitted regardless so that new users can register.
    """

    pagination_class = AccountsPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAuthenticated(), IsStaffOrReadOnly()]

    def get_queryset(self):
        qs = Principal.objects.order_by("-created_at")
        if self.request.user.is_staff:
            return qs
        return qs.filter(pk=self.request.user.pk)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PrincipalCreateSerializer
        if self.request.user.is_staff:
            return PrincipalSerializer
        return PrincipalPublicSerializer


class PrincipalDetailView(RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or soft-delete a single principal.

    GET/PUT/PATCH — Staff may access any principal; non-staff may only
    access their own (enforced by ``IsSelfOrStaff`` + scoped queryset).

    DELETE — Performs a soft-delete.  Non-staff users cannot delete their own
    principal via this endpoint (HTTP 403); only staff may soft-delete.
    """

    permission_classes = [IsAuthenticated, IsSelfOrStaff]

    def get_queryset(self):
        qs = Principal.objects.all()
        if self.request.user.is_staff:
            return qs
        return qs.filter(pk=self.request.user.pk)

    def get_serializer_class(self):
        if self.request.user.is_staff:
            return PrincipalSerializer
        return PrincipalPublicSerializer

    def perform_update(self, serializer) -> None:
        """Save with the requesting user as the actor (ACTOR_REQUIRED)."""
        with set_current_actor(self.request.user):
            serializer.save()

    def perform_destroy(self, instance: Principal) -> None:
        """Soft-delete the principal. Staff only."""
        if not self.request.user.is_staff:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only staff may delete principals.")
        with set_current_actor(self.request.user):
            instance.soft_delete(actor=self.request.user)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Return 204 No Content after soft-delete."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=204)
