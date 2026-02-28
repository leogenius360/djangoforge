"""Permission classes for the authz app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.api.permissions import BasePermission

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.views import View


class IsStaffOrReadOnly(BasePermission):
    """Allow read access to any authenticated user; write access requires ``is_staff``."""

    def has_permission(self, request: HttpRequest, view: View) -> bool:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.is_authenticated
        return request.user.is_authenticated and request.user.is_staff


class IsStaffUser(BasePermission):
    """Restrict access to staff users only."""

    message = "You must be a staff member to access this resource."

    def has_permission(self, request: HttpRequest, view: View) -> bool:
        return request.user.is_authenticated and request.user.is_staff
