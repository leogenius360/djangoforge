"""Shared test fixtures for the authz app."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import Principal
from apps.authz.enums import PermissionAction
from apps.authz.models import Permission, Role, RolePermission
from apps.authz.services import AssignmentService, RoleService

# ---------------------------------------------------------------
# Principals
# ---------------------------------------------------------------


@pytest.fixture
def user_principal(db):
    """A regular (non-staff) principal."""
    return Principal.objects.create_user(
        username="authz_testuser",
        password="TestPass123!",
    )


@pytest.fixture
def staff_principal(db):
    """A staff principal."""
    return Principal.objects.create_superuser(
        username="authz_staffuser",
        password="StaffPass123!",
    )


@pytest.fixture
def other_principal(db):
    """A second regular principal for multi-user tests."""
    return Principal.objects.create_user(
        username="authz_otheruser",
        password="OtherPass123!",
    )


# ---------------------------------------------------------------
# Content Types
# ---------------------------------------------------------------


@pytest.fixture
def principal_ct(db):
    """ContentType for the Principal model."""
    return ContentType.objects.get_for_model(Principal)


# ---------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------


@pytest.fixture
def read_perm(db, principal_ct):
    """A 'read' permission scoped to Principal."""
    return Permission.objects.create(
        codename="accounts.principal.read",
        name="Read Principal",
        content_type=principal_ct,
        action=PermissionAction.READ,
    )


@pytest.fixture
def update_perm(db, principal_ct):
    """An 'update' permission scoped to Principal."""
    return Permission.objects.create(
        codename="accounts.principal.update",
        name="Update Principal",
        content_type=principal_ct,
        action=PermissionAction.UPDATE,
    )


@pytest.fixture
def manage_perm(db, principal_ct):
    """A 'manage' permission scoped to Principal."""
    return Permission.objects.create(
        codename="accounts.principal.manage",
        name="Manage Principal",
        content_type=principal_ct,
        action=PermissionAction.MANAGE,
    )


# ---------------------------------------------------------------
# Roles
# ---------------------------------------------------------------


@pytest.fixture
def viewer_role(db, read_perm, principal_ct):
    """A viewer role with read permission."""
    role = Role.objects.create(
        codename="principal.viewer",
        name="Principal Viewer",
        content_type=principal_ct,
    )
    RolePermission.objects.create(role=role, permission=read_perm)
    return role


@pytest.fixture
def editor_role(db, update_perm, viewer_role, principal_ct):
    """An editor role (child of viewer) with update permission."""
    role = Role.objects.create(
        codename="principal.editor",
        name="Principal Editor",
        content_type=principal_ct,
        parent=viewer_role,
    )
    RolePermission.objects.create(role=role, permission=update_perm)
    return role


@pytest.fixture
def admin_role(db, manage_perm, editor_role, principal_ct):
    """An admin role (child of editor) with manage permission."""
    role = Role.objects.create(
        codename="principal.admin",
        name="Principal Admin",
        content_type=principal_ct,
        parent=editor_role,
    )
    RolePermission.objects.create(role=role, permission=manage_perm)
    return role


# ---------------------------------------------------------------
# Services
# ---------------------------------------------------------------


@pytest.fixture
def role_service():
    return RoleService()


@pytest.fixture
def assignment_service():
    return AssignmentService()
