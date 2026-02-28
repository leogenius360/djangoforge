"""
Permission classes for the DjangoForge API layer.

Drop-in replacements for ``rest_framework.permissions`` that work with
pure Django views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.views import View


class BasePermission:
    """Base class for all permissions."""

    def has_permission(self, request: HttpRequest, view: View) -> bool:
        return True

    def has_object_permission(self, request: HttpRequest, view: View, obj: object) -> bool:
        return True


class AllowAny(BasePermission):
    """Allow unrestricted access."""

    def has_permission(self, request: HttpRequest, view: View) -> bool:
        return True


class IsAuthenticated(BasePermission):
    """Allow access only to authenticated users."""

    def has_permission(self, request: HttpRequest, view: View) -> bool:
        user = getattr(request, "user", None)
        return bool(user and getattr(user, "is_authenticated", False))


class IsAdminUser(BasePermission):
    """Allow access only to admin/staff users."""

    def has_permission(self, request: HttpRequest, view: View) -> bool:
        user = getattr(request, "user", None)
        return bool(user and getattr(user, "is_staff", False))


class IsAuthenticatedOrReadOnly(BasePermission):
    """Allow read-only access to unauthenticated users, full access to authenticated users."""

    SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

    def has_permission(self, request: HttpRequest, view: View) -> bool:
        if request.method in self.SAFE_METHODS:
            return True
        user = getattr(request, "user", None)
        return bool(user and getattr(user, "is_authenticated", False))
