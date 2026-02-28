"""REST API permission classes for the auditing subsystem."""

from apps.core.api.permissions import BasePermission


class IsStaffUser(BasePermission):
    """Allow access to staff users only (``request.user.is_staff == True``)."""

    message = "You must be a staff member to access audit data."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
