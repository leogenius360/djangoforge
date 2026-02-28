"""Service tests for the authz app."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType

from apps.authz.enums import PolicyEffect
from apps.authz.exceptions import (
    DSLSyntaxError,
    InvalidAssignmentError,
    RoleHierarchyCycleError,
)
from apps.authz.models import Policy, Role
from apps.authz.services import (
    AuthorizationChecker,
    PolicyService,
)

# ---------------------------------------------------------------
# RoleService
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestRoleService:
    def test_create_role(self, role_service, principal_ct):
        role = role_service.create_role(
            codename="test.role",
            name="Test Role",
            content_type=principal_ct,
        )
        assert role.codename == "test.role"
        assert role.pk is not None

    def test_create_role_with_parent(self, role_service, viewer_role, principal_ct):
        child = role_service.create_role(
            codename="test.child",
            name="Child",
            content_type=principal_ct,
            parent=viewer_role,
        )
        assert child.parent == viewer_role

    def test_update_role(self, role_service, viewer_role):
        updated = role_service.update_role(viewer_role, name="Updated Viewer")
        assert updated.name == "Updated Viewer"

    def test_update_system_role_raises(self, role_service, principal_ct):
        system_role = role_service.create_role(
            codename="system.role",
            name="System",
            content_type=principal_ct,
            is_system=True,
        )
        with pytest.raises(ValueError, match="system role"):
            role_service.update_role(system_role, name="Nope")

    def test_delete_role(self, role_service, viewer_role):
        role_service.delete_role(viewer_role)
        assert viewer_role.is_deleted

    def test_delete_system_role_raises(self, role_service, principal_ct):
        system_role = role_service.create_role(
            codename="system.role2",
            name="System 2",
            content_type=principal_ct,
            is_system=True,
        )
        with pytest.raises(ValueError, match="system role"):
            role_service.delete_role(system_role)

    def test_add_permission(self, role_service, viewer_role, update_perm):
        rp = role_service.add_permission(viewer_role, update_perm)
        assert rp.role == viewer_role
        assert rp.permission == update_perm

    def test_add_permission_idempotent(self, role_service, viewer_role, read_perm):
        rp1 = role_service.add_permission(viewer_role, read_perm)
        rp2 = role_service.add_permission(viewer_role, read_perm)
        assert rp1.pk == rp2.pk

    def test_remove_permission(self, role_service, viewer_role, read_perm):
        role_service.remove_permission(viewer_role, read_perm)
        assert viewer_role.role_permissions.count() == 0

    def test_cycle_detection_self(self, role_service, viewer_role):
        with pytest.raises(RoleHierarchyCycleError):
            role_service.update_role(viewer_role, parent=viewer_role)

    def test_cycle_detection_descendant(self, role_service, viewer_role, editor_role, admin_role):
        with pytest.raises(RoleHierarchyCycleError):
            role_service.update_role(viewer_role, parent=admin_role)


# ---------------------------------------------------------------
# AssignmentService
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestAssignmentService:
    def test_assign_role(self, assignment_service, user_principal, viewer_role, staff_principal):
        assignment = assignment_service.assign_role(
            principal=user_principal,
            role=viewer_role,
            resource=staff_principal,
        )
        assert assignment.principal == user_principal
        assert assignment.role == viewer_role

    def test_assign_role_idempotent(self, assignment_service, user_principal, viewer_role, staff_principal):
        a1 = assignment_service.assign_role(
            principal=user_principal,
            role=viewer_role,
            resource=staff_principal,
        )
        a2 = assignment_service.assign_role(
            principal=user_principal,
            role=viewer_role,
            resource=staff_principal,
        )
        assert a1.pk == a2.pk

    def test_assign_role_scope_mismatch(self, assignment_service, user_principal, staff_principal):
        # Create a role scoped to a different content type

        wrong_ct = ContentType.objects.get(app_label="authz", model="role")
        role = Role.objects.create(
            codename="wrong.scope",
            name="Wrong Scope",
            content_type=wrong_ct,
        )
        with pytest.raises(InvalidAssignmentError):
            assignment_service.assign_role(
                principal=user_principal,
                role=role,
                resource=staff_principal,
            )

    def test_revoke_role(self, assignment_service, user_principal, viewer_role, staff_principal):
        assignment_service.assign_role(
            principal=user_principal,
            role=viewer_role,
            resource=staff_principal,
        )
        revoked = assignment_service.revoke_role(
            principal=user_principal,
            role=viewer_role,
            resource=staff_principal,
        )
        assert revoked is True

    def test_revoke_nonexistent_returns_false(self, assignment_service, user_principal, viewer_role, staff_principal):
        revoked = assignment_service.revoke_role(
            principal=user_principal,
            role=viewer_role,
            resource=staff_principal,
        )
        assert revoked is False


# ---------------------------------------------------------------
# PolicyService
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyService:
    def test_create_policy(self, principal_ct):
        svc = PolicyService()
        policy = svc.create_policy(
            codename="test.policy",
            name="Test Policy",
            effect=PolicyEffect.ALLOW,
            condition='principal.kind == "user"',
            content_type=principal_ct,
        )
        assert policy.pk is not None
        assert policy.codename == "test.policy"

    def test_create_policy_invalid_condition(self, principal_ct):
        svc = PolicyService()
        with pytest.raises(DSLSyntaxError):
            svc.create_policy(
                codename="bad.policy",
                name="Bad",
                effect=PolicyEffect.ALLOW,
                condition="a ==",  # syntax error
                content_type=principal_ct,
            )

    def test_validate_condition_ok(self):
        svc = PolicyService()
        assert svc.validate_condition('action == "read"') is True

    def test_validate_condition_invalid(self):
        svc = PolicyService()
        with pytest.raises(DSLSyntaxError):
            svc.validate_condition("==bad==")

    def test_update_policy(self, principal_ct):
        svc = PolicyService()
        policy = svc.create_policy(
            codename="upd.policy",
            name="Original",
            effect=PolicyEffect.ALLOW,
            condition="true",
            content_type=principal_ct,
        )
        updated = svc.update_policy(policy, name="Updated")
        assert updated.name == "Updated"

    def test_delete_system_policy_raises(self, principal_ct):
        svc = PolicyService()
        policy = svc.create_policy(
            codename="sys.policy",
            name="System",
            effect=PolicyEffect.DENY,
            condition="true",
            content_type=principal_ct,
            is_system=True,
        )
        with pytest.raises(ValueError, match="system policy"):
            svc.delete_policy(policy)


# ---------------------------------------------------------------
# AuthorizationChecker
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestAuthorizationChecker:
    def test_rbac_grant(self, assignment_service, user_principal, viewer_role, staff_principal):
        assignment_service.assign_role(
            principal=user_principal,
            role=viewer_role,
            resource=staff_principal,
        )

        checker = AuthorizationChecker()
        decision = checker.check(
            principal=user_principal,
            action="read",
            resource=staff_principal,
        )
        assert decision.allowed is True
        assert "role" in decision.reason.lower()

    def test_rbac_hierarchy_grant(
        self,
        assignment_service,
        user_principal,
        admin_role,
        staff_principal,
    ):
        """Admin role (inherits editor + viewer) should grant read access."""
        assignment_service.assign_role(
            principal=user_principal,
            role=admin_role,
            resource=staff_principal,
        )

        checker = AuthorizationChecker()
        decision = checker.check(
            principal=user_principal,
            action="read",
            resource=staff_principal,
        )
        assert decision.allowed is True

    def test_default_deny(self, user_principal, staff_principal):
        checker = AuthorizationChecker()
        decision = checker.check(
            principal=user_principal,
            action="read",
            resource=staff_principal,
        )
        assert decision.allowed is False
        assert "no matching" in decision.reason.lower()

    def test_deny_policy_overrides_rbac(
        self,
        assignment_service,
        user_principal,
        viewer_role,
        staff_principal,
        principal_ct,
    ):
        # Grant via RBAC
        assignment_service.assign_role(
            principal=user_principal,
            role=viewer_role,
            resource=staff_principal,
        )
        # Create explicit deny policy
        Policy.objects.create(
            codename="deny.all.read",
            name="Deny All Read",
            effect=PolicyEffect.DENY,
            condition="true",
            content_type=principal_ct,
            action="read",
        )

        checker = AuthorizationChecker()
        decision = checker.check(
            principal=user_principal,
            action="read",
            resource=staff_principal,
        )
        assert decision.allowed is False
        assert "denied by policy" in decision.reason.lower()

    def test_allow_policy_grants_without_rbac(self, user_principal, staff_principal, principal_ct):
        Policy.objects.create(
            codename="allow.staff.read",
            name="Allow Staff Read",
            effect=PolicyEffect.ALLOW,
            condition="true",
            content_type=principal_ct,
            action="read",
        )

        checker = AuthorizationChecker()
        decision = checker.check(
            principal=user_principal,
            action="read",
            resource=staff_principal,
        )
        assert decision.allowed is True
        assert "policy" in decision.reason.lower()

    def test_evaluation_time_is_recorded(self, user_principal, staff_principal):
        checker = AuthorizationChecker()
        decision = checker.check(
            principal=user_principal,
            action="read",
            resource=staff_principal,
        )
        assert decision.evaluation_time_ms >= 0
