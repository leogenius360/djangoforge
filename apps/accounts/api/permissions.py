"""
DRF permissions for the accounts app.

Permissions
-----------
IsStaffOrReadOnly
    Write operations require ``is_staff`` when ``accounts_settings.API_REQUIRE_STAFF``
    is True.  Read operations are allowed for any authenticated user.

IsOwnerOrStaff
    Object-level permission that grants access to the owning user or staff.

IsSelfOrStaff
    Object-level permission for Principal objects: allows access when the object
    IS the requesting principal, or the requester is staff.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

from apps.accounts.settings import accounts_settings


class IsStaffOrReadOnly(BasePermission):
    """
    Allow read access to any authenticated user.

    Write access is restricted to staff when ``API_REQUIRE_STAFF`` is True.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True

        if accounts_settings.API_REQUIRE_STAFF:
            return bool(request.user.is_staff)

        return True


class IsOwnerOrStaff(BasePermission):
    """
    Object-level permission: allow the owner or staff.

    Expects the object to have an ``owner`` or ``principal`` FK pointing to a
    Principal.  For UserAccount the principal is the "owner".
    """

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_staff:
            return True

        # ServiceAccount / APIClient / AgentAccount: check owner FK
        if hasattr(obj, "owner_id") and obj.owner_id is not None:
            return obj.owner_id == request.user.pk

        # UserAccount: the requesting principal IS the account's principal
        if hasattr(obj, "principal_id"):
            return obj.principal_id == request.user.pk

        return False


class IsSelfOrStaff(BasePermission):
    """
    Object-level permission for Principal objects.

    Grants access when the object's pk matches the requesting user's pk
    (i.e. the principal is accessing their own record) or the requester
    is staff.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_staff:
            return True

        return getattr(obj, "pk", None) == request.user.pk
