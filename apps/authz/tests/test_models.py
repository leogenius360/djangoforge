"""Model tests for the authz app."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.utils import timezone

from apps.authz.enums import PermissionAction, PolicyEffect
from apps.authz.models import Permission, Policy, RoleAssignment

# ---------------------------------------------------------------
# Permission
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestPermission:
    def test_build_codename(self, principal_ct):
        codename = Permission.build_codename(principal_ct, PermissionAction.READ)
        assert codename == "accounts.principal.read"

    def test_str(self, read_perm):
        assert str(read_perm) == "accounts.principal.read"

    def test_unique_ct_action_constraint(self, principal_ct, read_perm):
        with pytest.raises(IntegrityError):
            Permission.objects.create(
                codename="accounts.principal.read_dup",
                name="Duplicate",
                content_type=principal_ct,
                action=PermissionAction.READ,
            )


# ---------------------------------------------------------------
# Role hierarchy
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestRoleHierarchy:
    def test_flat_role_has_no_ancestors(self, viewer_role):
        assert viewer_role.get_ancestors() == []

    def test_child_lists_parent_as_ancestor(self, editor_role, viewer_role):
        ancestors = editor_role.get_ancestors()
        assert len(ancestors) == 1
        assert ancestors[0] == viewer_role

    def test_grandchild_lists_two_ancestors(self, admin_role, editor_role, viewer_role):
        ancestors = admin_role.get_ancestors()
        assert len(ancestors) == 2
        assert editor_role in ancestors
        assert viewer_role in ancestors

    def test_include_self(self, admin_role):
        ancestors = admin_role.get_ancestors(include_self=True)
        assert admin_role in ancestors

    def test_get_descendants(self, viewer_role, editor_role, admin_role):
        descendants = viewer_role.get_descendants()
        assert len(descendants) == 2
        assert editor_role in descendants
        assert admin_role in descendants

    def test_get_all_permission_ids_includes_inherited(self, admin_role, read_perm, update_perm, manage_perm):
        perm_ids = admin_role.get_all_permission_ids()
        assert read_perm.pk in perm_ids
        assert update_perm.pk in perm_ids
        assert manage_perm.pk in perm_ids

    def test_viewer_only_has_own_permissions(self, viewer_role, read_perm):
        perm_ids = viewer_role.get_all_permission_ids()
        assert perm_ids == {read_perm.pk}


# ---------------------------------------------------------------
# RoleAssignment
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestRoleAssignment:
    def test_is_expired_false_when_no_expiry(self, user_principal, viewer_role, staff_principal):
        ct = ContentType.objects.get_for_model(staff_principal)
        assignment = RoleAssignment.objects.create(
            principal=user_principal,
            role=viewer_role,
            content_type=ct,
            object_id=staff_principal.pk,
        )
        assert assignment.is_expired is False

    def test_is_expired_true_when_past(self, user_principal, viewer_role, staff_principal):
        ct = ContentType.objects.get_for_model(staff_principal)
        assignment = RoleAssignment.objects.create(
            principal=user_principal,
            role=viewer_role,
            content_type=ct,
            object_id=staff_principal.pk,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert assignment.is_expired is True

    def test_active_queryset_excludes_expired(self, user_principal, viewer_role, staff_principal):
        ct = ContentType.objects.get_for_model(staff_principal)
        RoleAssignment.objects.create(
            principal=user_principal,
            role=viewer_role,
            content_type=ct,
            object_id=staff_principal.pk,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        active = RoleAssignment.objects.active().for_principal(user_principal)
        assert active.count() == 0


# ---------------------------------------------------------------
# Policy
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestPolicy:
    def test_enabled_queryset(self, principal_ct):
        Policy.objects.create(
            codename="test-enabled",
            name="Enabled",
            effect=PolicyEffect.ALLOW,
            condition="true",
            content_type=principal_ct,
            is_enabled=True,
        )
        Policy.objects.create(
            codename="test-disabled",
            name="Disabled",
            effect=PolicyEffect.ALLOW,
            condition="true",
            content_type=principal_ct,
            is_enabled=False,
        )
        assert Policy.objects.enabled().count() == 1

    def test_for_action_matches_empty_action(self, principal_ct):
        Policy.objects.create(
            codename="any-action",
            name="Any",
            effect=PolicyEffect.ALLOW,
            condition="true",
            content_type=principal_ct,
            action="",
        )
        assert Policy.objects.for_action("read").count() == 1

    def test_for_action_matches_specific_action(self, principal_ct):
        Policy.objects.create(
            codename="read-only",
            name="Read Only",
            effect=PolicyEffect.ALLOW,
            condition="true",
            content_type=principal_ct,
            action="read",
        )
        assert Policy.objects.for_action("read").count() == 1
        assert Policy.objects.for_action("write").count() == 0
