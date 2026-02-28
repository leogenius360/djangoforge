"""URL configuration for the authz app."""

from django.urls import path

from .views import (
    CheckPermissionView,
    PermissionDetailView,
    PermissionListCreateView,
    PolicyDetailView,
    PolicyListCreateView,
    RoleAssignmentDetailView,
    RoleAssignmentListCreateView,
    RoleDetailView,
    RoleListCreateView,
    RolePermissionsView,
)

app_name = "authz"

urlpatterns = [
    # Permissions
    path("permissions/", PermissionListCreateView.as_view(), name="permission-list"),
    path(
        "permissions/<uuid:pk>/",
        PermissionDetailView.as_view(),
        name="permission-detail",
    ),
    # Roles
    path("roles/", RoleListCreateView.as_view(), name="role-list"),
    path("roles/<uuid:pk>/", RoleDetailView.as_view(), name="role-detail"),
    path(
        "roles/<uuid:pk>/permissions/",
        RolePermissionsView.as_view(),
        name="role-permissions",
    ),
    # Role assignments
    path("assignments/", RoleAssignmentListCreateView.as_view(), name="assignment-list"),
    path(
        "assignments/<uuid:pk>/",
        RoleAssignmentDetailView.as_view(),
        name="assignment-detail",
    ),
    # Policies
    path("policies/", PolicyListCreateView.as_view(), name="policy-list"),
    path("policies/<uuid:pk>/", PolicyDetailView.as_view(), name="policy-detail"),
    # Permission check
    path("check/", CheckPermissionView.as_view(), name="check-permission"),
]
